import { Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as Ses from 'aws-cdk-lib/aws-ses';
import * as Actions from 'aws-cdk-lib/aws-ses-actions';
import * as Sns from 'aws-cdk-lib/aws-sns';
import * as IAm from "aws-cdk-lib/aws-iam";
import * as Route53 from 'aws-cdk-lib/aws-route53';
import * as Events from "aws-cdk-lib/aws-events";
import * as Targets from "aws-cdk-lib/aws-events-targets";
import * as path from "path";
import {
    CORS_ALLOWED_ORIGINS,
    EMAIL_DOMAIN_NAME, FRONTEND_DOMAIN_NAME, HOSTED_ZONE_NAME,
    MAILBOX_TTL
} from "./constants";
import { StaticWebpage } from "./Constructs/StaticWebpage";
import { AuthorisingApiConstruct } from "./Constructs/AuthorisingApi";
import { StorageConstruct } from "./Constructs/Storage";
import { DisposableEmailLambdaConstruct } from "./Constructs/DisposableEmailLambda";

/**
 * This Stack deploys a disposable email service. consists of:
 * - 8 backend lambdas
 * - 1 frontend s3 bucket
 * - 1 backend s3 bucket for email storage
 * - api gateway protected by cognito
 * - 3 dynamodb tables: emails, addresses, replyToAddresses
 * - 1 sns topic
 * You will need to manually create a identity in SES and verify your domain
 * after deployment in SES -> Email Receiving check if emails to your EMAIL_DOMAIN_NAME
 * are covered by the rule set
 */
export class DisposableEmailCdkStack extends Stack {
    constructor( scope: Construct, id: string, props?: StackProps ) {

        super( scope, id, props );

        const mainHostedZone =
            Route53.HostedZone.fromLookup( this, 'Zone',
                { domainName: HOSTED_ZONE_NAME } );

        // front end
        new StaticWebpage( this, 'StaticWebpage', {
            domain: FRONTEND_DOMAIN_NAME,
            hostedZone: mainHostedZone,
            stack: this,
            staticFilesPath: path.join( __dirname, '../src/StaticWebsite/' ),
        } )

        const storage = new StorageConstruct( this, 'storage' )

        // Create SNS topic for new SES email notifications
        const emailNotificationTopic = new Sns.Topic( this, 'emailNotificationTopic', {
            topicName: 'disposable-email-notification-topic',
            displayName: 'Disposable Email Notification Topic',
        } );

        emailNotificationTopic.addToResourcePolicy( new IAm.PolicyStatement( {
            actions: [ 'sns:Publish' ],
            resources: [ emailNotificationTopic.topicArn ],
            principals: [ new IAm.ServicePrincipal( 'ses.amazonaws.com' ) ],
        } ) );

        const lambdas = new DisposableEmailLambdaConstruct( this, 'backendLambdas',
            {
                domain: EMAIL_DOMAIN_NAME,
                mailboxTtl: MAILBOX_TTL,
                corsAllowedOrigins: CORS_ALLOWED_ORIGINS,
                storageConstruct: storage,
                emailLambdaSnsTopic: emailNotificationTopic,
            } );

        new AuthorisingApiConstruct( this, 'api', {
            createEmailLambda: lambdas.createEmailLambda,
            getEmailFileLambda: lambdas.getEmailFileLambda,
            getEmailsListLambda: lambdas.getEmailsListLambda,
            sendEmailLambda: lambdas.sendEmailLambda,
            changeAddressSettingsLambda: lambdas.changeAddressSettingsLambda,
        } )

        // Allow SES to put emails into the S3 bucket
        storage.emailStorageBucket.addToResourcePolicy( new IAm.PolicyStatement( {
            actions: [ 's3:PutObject' ],
            resources: [ `${ storage.emailStorageBucket.bucketArn }/*` ],
            principals: [ new IAm.ServicePrincipal( 'ses.amazonaws.com' ) ],
        } ) );

        new Ses.ReceiptRuleSet( this, 'RuleSet', {
            rules: [
                {
                    recipients: [ EMAIL_DOMAIN_NAME ],
                    actions: [
                        new Actions.Lambda( {
                            function: lambdas.incomingMailCheckLambda,
                            invocationType: Actions.LambdaInvocationType.REQUEST_RESPONSE,
                        } ),
                        new Actions.S3( {
                            bucket: storage.emailStorageBucket,
                            topic: emailNotificationTopic,
                        } )
                    ]
                }
            ]
        } );

        // Schedule a cleanup of the email storage bucket and
        // dynamodb tables every 30 minutes
        new Events.Rule( this, 'cleanupRule', {
            schedule: Events.Schedule.expression( 'rate(30 minutes)' ),
            targets: [
                new Targets.LambdaFunction( lambdas.cleanUpLambda )
            ],
        } );
    }
}
