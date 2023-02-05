import { Construct } from "constructs";
import { Duration } from "aws-cdk-lib";
import * as Lambda from "aws-cdk-lib/aws-lambda";
import * as Cognito from "aws-cdk-lib/aws-cognito";
import { RemovalPolicy } from "aws-cdk-lib";
import * as ApiGateway from "aws-cdk-lib/aws-apigateway";
import * as IAm from "aws-cdk-lib/aws-iam";
import { CORS_ALLOWED_ORIGINS } from "../constants";

export type ApiGatewayConstructProps = {
    createEmailLambda: Lambda.Function;
    getEmailFileLambda: Lambda.Function;
    getEmailsListLambda: Lambda.Function;
    sendEmailLambda: Lambda.Function;
    changeAddressSettingsLambda: Lambda.Function;
}

export class AuthorisingApiConstruct extends Construct {

    readonly apiGw: ApiGateway.RestApi;
    readonly cognitoUserPool: Cognito.UserPool;

    constructor( scope: Construct, id: string, props: ApiGatewayConstructProps ) {
        super( scope, id );

        this.cognitoUserPool = new Cognito.UserPool( this, 'userPool', {
            userPoolName: 'disposable-email-user-pool',
            removalPolicy: RemovalPolicy.DESTROY,
            selfSignUpEnabled: false,
            signInAliases: { email: true },
            autoVerify: { email: true },
            passwordPolicy: {
                minLength: 6,
                requireLowercase: false,
                requireDigits: false,
                requireUppercase: false,
                requireSymbols: false,
            },
            accountRecovery: Cognito.AccountRecovery.EMAIL_ONLY,
        } );

        this.cognitoUserPool.addClient( 'disposable-email-user-pool-client', {
            userPoolClientName: 'disposable-email-user-pool-client',
            supportedIdentityProviders: [ Cognito.UserPoolClientIdentityProvider.COGNITO ],
        } )

        const authorizer = new ApiGateway.CognitoUserPoolsAuthorizer( this,
            'cognitoAuthorizer', {
                cognitoUserPools: [ this.cognitoUserPool ],
                resultsCacheTtl: Duration.seconds( 0 ),
            } );

        this.apiGw = new ApiGateway.RestApi( this, 'api', {
            restApiName: 'DisposableEmailApi',
            description: 'This service provides disposable email addresses',
            endpointTypes: [ ApiGateway.EndpointType.REGIONAL ],
            defaultCorsPreflightOptions: {
                allowOrigins: CORS_ALLOWED_ORIGINS,
                allowMethods: [ "GET", "POST", "OPTIONS" ],
                allowHeaders: ApiGateway.Cors.DEFAULT_HEADERS,
                allowCredentials: true,
            },
            defaultMethodOptions: {
                authorizationType: ApiGateway.AuthorizationType.COGNITO,
                authorizer: authorizer,
            },
            deploy: true
        } );

        const createEmailMethod = this.apiGw.root.addResource( 'create' )
            .addMethod( 'GET',
                new ApiGateway.LambdaIntegration( props.createEmailLambda )
            );

        const destinationResource = this.apiGw.root.addResource( '{destination}' );
        const listEmailsMethod = destinationResource.addMethod(
            'GET',
            new ApiGateway.LambdaIntegration( props.getEmailsListLambda ) );

        const changeSettingsMethod = destinationResource.addMethod(
            'POST',
            new ApiGateway.LambdaIntegration( props.changeAddressSettingsLambda ) );

        const getEmailMethod = destinationResource.addResource( '{messageId}' )
            .addMethod( 'GET',
                new ApiGateway.LambdaIntegration( props.getEmailFileLambda ) );

        const sendEmailMethod = this.apiGw.root.addResource( 'send' )
            .addMethod( 'POST',
                new ApiGateway.LambdaIntegration( props.sendEmailLambda ) );

        props.createEmailLambda.addPermission( 'createEmailLambdaPermission', {
            principal: new IAm.ServicePrincipal( 'apigateway.amazonaws.com' ),
            sourceArn: createEmailMethod.methodArn,
        } );

        props.getEmailsListLambda.addPermission( 'getEmailsListLambdaPermission', {
            principal: new IAm.ServicePrincipal( 'apigateway.amazonaws.com' ),
            sourceArn: listEmailsMethod.methodArn,
        } );

        props.getEmailFileLambda.addPermission( 'getEmailFileLambdaPermission', {
            principal: new IAm.ServicePrincipal( 'apigateway.amazonaws.com' ),
            sourceArn: getEmailMethod.methodArn,
        } );

        props.sendEmailLambda.addPermission( 'sendEmailLambdaPermission', {
            principal: new IAm.ServicePrincipal( 'apigateway.amazonaws.com' ),
            sourceArn: sendEmailMethod.methodArn,
        } );

        props.changeAddressSettingsLambda.addPermission( 'changeSettingsLambdaPermission', {
            principal: new IAm.ServicePrincipal( 'apigateway.amazonaws.com' ),
            sourceArn: changeSettingsMethod.methodArn,
        } );
    }
}