// create a construct that represents a lambda function

import { Construct } from "constructs";
import * as Lambda from "aws-cdk-lib/aws-lambda";
import { PolicyStatement } from "aws-cdk-lib/aws-iam";
import { Duration } from "aws-cdk-lib";
import { StorageConstruct } from "./Storage";
import * as IAm from "aws-cdk-lib/aws-iam";
import { SnsEventSource } from "aws-cdk-lib/aws-lambda-event-sources";
import { Topic } from "aws-cdk-lib/aws-sns";

export type LambdaConstructProps = {
    domain: string;
    mailboxTtl: number;
    corsAllowedOrigins: string[];
    storageConstruct: StorageConstruct;
    emailLambdaSnsTopic: Topic;
}

export class DisposableEmailLambdaConstruct extends Construct {

    readonly cleanUpLambda: Lambda.Function;
    readonly createEmailLambda: Lambda.Function;
    readonly getEmailFileLambda: Lambda.Function;
    readonly getEmailsListLambda: Lambda.Function;
    readonly incomingMailCheckLambda: Lambda.Function;
    readonly storeEmailLambda: Lambda.Function;
    readonly sendEmailLambda: Lambda.Function;
    readonly changeAddressSettingsLambda: Lambda.Function;

    constructor( scope: Construct, id: string, props: LambdaConstructProps ) {
        super( scope, id );

        /**
         * incomingMailCheckLambda
         * called by SES when an email for *@EMAIL_DOMAIN_NAME is received to evaluate further processing
         * has access to:
         *     DynamoDB table: AddressesTable, EmailsTable, ReplyAddressesTable
         */
        this.incomingMailCheckLambda = new Lambda.Function( this, 'incomingMailCheckLambda', {
            code: Lambda.Code.fromAsset( 'src/IncomingMailCheckFunction/' ),
            handler: "IncomingMailCheckFunction.lambda_handler",
            runtime: Lambda.Runtime.PYTHON_3_9,
            architecture: Lambda.Architecture.ARM_64,
            environment: {
                'addresses_table_name': props.storageConstruct.disposableAddressesTable.tableName,
                'reply_addresses_table_name': props.storageConstruct.disposableReplyAddressesTable.tableName,
            }
        } );
        props.storageConstruct.disposableAddressesTable.grantReadData( this.incomingMailCheckLambda );
        props.storageConstruct.disposableReplyAddressesTable.grantReadData( this.incomingMailCheckLambda );
        this.incomingMailCheckLambda.addPermission( 'snsPermission', {
            principal: new IAm.ServicePrincipal( 'sns.amazonaws.com' )
        } );

        /**
         * storeEmailLambda
         * When incomingMailCheckLambda decides for further processing, the Email is stored to S3 by SES
         * and SES call an SNS topic which triggers this lambda function
         * This lambda checks if an email was sent to a known disposable address and if so,
         * it stores the email in the EmailsTable. If the email was sent to a proxy address, it finds
         * out the actual external address and redirects the email to it.
         * has access to:
         *     DynamoDB table: AddressesTable, EmailsTable, ReplyAddressesTable
         *     S3 bucket: EmailBucket
         *     SES: SendRawEmail
         *
         */
        this.storeEmailLambda = new Lambda.Function( this, 'StoreEmailLambda', {
            code: Lambda.Code.fromAsset( 'src/StoreEmailFunction/' ),
            handler: "StoreEmailFunction.lambda_handler",
            runtime: Lambda.Runtime.PYTHON_3_9,
            architecture: Lambda.Architecture.ARM_64,
            timeout: Duration.minutes( 5 ),
            environment: {
                "valid_domains": props.domain,
                'addresses_table_name': props.storageConstruct.disposableAddressesTable.tableName,
                'emails_table_name': props.storageConstruct.disposableEmailsTable.tableName,
                'reply_addresses_table_name': props.storageConstruct.disposableReplyAddressesTable.tableName,
                'emails_bucket_name': props.storageConstruct.emailStorageBucket.bucketName,
            }
        } );
        props.storageConstruct.disposableReplyAddressesTable.grantReadWriteData( this.storeEmailLambda );
        props.storageConstruct.emailStorageBucket.grantReadWrite( this.storeEmailLambda );
        props.storageConstruct.disposableEmailsTable.grantWriteData( this.storeEmailLambda );
        props.storageConstruct.disposableAddressesTable.grantReadData( this.storeEmailLambda );
        this.storeEmailLambda.addEventSource( new SnsEventSource( props.emailLambdaSnsTopic ) );
        this.storeEmailLambda.addToRolePolicy( new PolicyStatement( {
            actions: ["ses:SendRawEmail" ],
            resources: [ "*" ]
        } ) );

        /**
         * createEmailLambda
         * Creates a disposable email address and returns all the addresses a user owns and their ttls
         * has access to:
         *     DynamoDB table: AddressesTable
         */
        this.createEmailLambda = new Lambda.Function( this, 'createEmailLambda', {
            code: Lambda.Code.fromAsset( 'src/CreateEmailFunction/' ),
            handler: "CreateEmailFunction.lambda_handler",
            runtime: Lambda.Runtime.PYTHON_3_9,
            architecture: Lambda.Architecture.ARM_64,
            environment: {
                "mailbox_ttl": props.mailboxTtl.toString(),
                "valid_domains": props.domain,
                "cors_allowed_origins": props.corsAllowedOrigins.join( "," ),
                "addresses_table_name": props.storageConstruct.disposableAddressesTable.tableName,
            }
        } );
        props.storageConstruct.disposableAddressesTable.grantReadWriteData( this.createEmailLambda );

        /**
         * getEmailsListLambda
         * Return all emails for a given address. does not return the actual email content
         * only the metadata saved in the EmailsTable
         * has access to:
         *     DynamoDB table: EmailsTable, AddressesTable
         */
        this.getEmailsListLambda = new Lambda.Function( this, 'getEmailsListLambda', {
            code: Lambda.Code.fromAsset( 'src/GetEmailsListFunction/' ),
            handler: "GetEmailsListFunction.lambda_handler",
            runtime: Lambda.Runtime.PYTHON_3_9,
            architecture: Lambda.Architecture.ARM_64,
            environment: {
                "cors_allowed_origins": props.corsAllowedOrigins.join( "," ),
                "emails_table_name": props.storageConstruct.disposableEmailsTable.tableName,
                "addresses_table_name": props.storageConstruct.disposableAddressesTable.tableName,
            }
        } );
        props.storageConstruct.disposableAddressesTable.grantReadData( this.getEmailsListLambda );
        props.storageConstruct.disposableEmailsTable.grantReadData( this.getEmailsListLambda );

        /**
         * getEmailFileLambda
         * Returns the actual email content for a given email id
         * has access to:
         *     DynamoDB table: EmailsTable, AddressesTable
         *     S3 bucket: EmailBucket
         */
        this.getEmailFileLambda = new Lambda.Function( this, 'getEmailFileLambda', {
            code: Lambda.Code.fromAsset( 'src/GetEmailFileFunction/' ),
            handler: "GetEmailFileFunction.lambda_handler",
            runtime: Lambda.Runtime.PYTHON_3_9,
            architecture: Lambda.Architecture.ARM_64,
            environment: {
                "cors_allowed_origins": props.corsAllowedOrigins.join( "," ),
                "emails_table_name": props.storageConstruct.disposableEmailsTable.tableName,
                "addresses_table_name": props.storageConstruct.disposableAddressesTable.tableName,
                "emails_bucket_name": props.storageConstruct.emailStorageBucket.bucketName,
            }
        } );
        props.storageConstruct.disposableEmailsTable.grantReadWriteData( this.getEmailFileLambda );
        props.storageConstruct.disposableAddressesTable.grantReadData( this.getEmailFileLambda );
        props.storageConstruct.emailStorageBucket.grantRead( this.getEmailFileLambda );

        /**
         * cleanUpLambda
         * Deletes all addresses, their emails and reply_addresses that have reached their ttl
         * from the database and the email storage bucket
         * has access to:
         *     DynamoDB table: AddressesTable, EmailsTable, ReplyAddressesTable
         *     S3 bucket: EmailBucket
         */
        this.cleanUpLambda = new Lambda.Function( this, 'cleanUpLambda', {
            code: Lambda.Code.fromAsset( 'src/CleanUpFunction/' ),
            handler: "CleanUpFunction.lambda_handler",
            runtime: Lambda.Runtime.PYTHON_3_9,
            architecture: Lambda.Architecture.ARM_64,
            timeout: Duration.minutes( 1 ),
            environment: {
                "addresses_table_name": props.storageConstruct.disposableAddressesTable.tableName,
                "emails_table_name": props.storageConstruct.disposableEmailsTable.tableName,
                "reply_addresses_table_name": props.storageConstruct.disposableReplyAddressesTable.tableName,
                "emails_bucket_name": props.storageConstruct.emailStorageBucket.bucketName,
            }
        } );
        props.storageConstruct.disposableReplyAddressesTable.grantReadWriteData( this.cleanUpLambda );
        props.storageConstruct.disposableAddressesTable.grantReadWriteData( this.cleanUpLambda );
        props.storageConstruct.disposableEmailsTable.grantReadWriteData( this.cleanUpLambda );
        props.storageConstruct.emailStorageBucket.grantDelete( this.cleanUpLambda );

        /**
         * sendEmailLambda
         * Sends an email based on given parameters
         * has access to:
         *     DynamoDB table: AddressesTable, EmailsTable
         *     SES: SendRawEmail
         */
        this.sendEmailLambda = new Lambda.Function( this, 'sendEmailLambda', {
            code: Lambda.Code.fromAsset( 'src/SendEmailFunction/' ),
            handler: "SendEmailFunction.lambda_handler",
            runtime: Lambda.Runtime.PYTHON_3_9,
            architecture: Lambda.Architecture.ARM_64,
            timeout: Duration.minutes( 1 ),
            environment: {
                "cors_allowed_origins": props.corsAllowedOrigins.join( "," ),
                "emails_table_name": props.storageConstruct.disposableEmailsTable.tableName,
                "addresses_table_name": props.storageConstruct.disposableAddressesTable.tableName,
            }
        } );
        props.storageConstruct.disposableAddressesTable.grantReadData( this.sendEmailLambda );
        props.storageConstruct.disposableEmailsTable.grantReadData( this.sendEmailLambda );
        this.sendEmailLambda.addToRolePolicy( new PolicyStatement( {
            actions: [ "ses:SendRawEmail" ],
            resources: [ "*" ],
        } ) );

        /**
         * changeAddressSettingsLambda
         * changes settings for a given address, for example to delete, or increase the ttl
         * has access to:
         *     DynamoDB table: AddressesTable, EmailsTable
         */
        this.changeAddressSettingsLambda = new Lambda.Function( this, 'changeAddressSettingsLambda', {
            code: Lambda.Code.fromAsset( 'src/ChangeAddressSettingsFunction/' ),
            handler: "ChangeAddressSettingsFunction.lambda_handler",
            runtime: Lambda.Runtime.PYTHON_3_9,
            architecture: Lambda.Architecture.ARM_64,
            environment: {
                "mailbox_ttl": props.mailboxTtl.toString(),
                "cors_allowed_origins": props.corsAllowedOrigins.join( "," ),
                "addresses_table_name": props.storageConstruct.disposableAddressesTable.tableName,
            }
        } );
        props.storageConstruct.disposableAddressesTable.grantReadWriteData( this.changeAddressSettingsLambda );
    }
}