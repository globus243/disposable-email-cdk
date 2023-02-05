import { Construct } from "constructs";
import { RemovalPolicy } from "aws-cdk-lib";
import * as DynamoDb from "aws-cdk-lib/aws-dynamodb";
import * as S3 from "aws-cdk-lib/aws-s3";

export class StorageConstruct extends Construct {

    readonly emailStorageBucket: S3.Bucket;
    readonly disposableAddressesTable: DynamoDb.Table;
    readonly disposableEmailsTable: DynamoDb.Table;
    readonly disposableReplyAddressesTable: DynamoDb.Table;

    constructor( scope: Construct, id: string ) {
        super( scope, id );

        this.disposableAddressesTable = new DynamoDb.Table( this, 'disposableAddressesTable', {
            partitionKey: {
                name: 'address',
                type: DynamoDb.AttributeType.STRING
            },
            billingMode: DynamoDb.BillingMode.PAY_PER_REQUEST,
            removalPolicy: RemovalPolicy.DESTROY,
        } );

        this.disposableEmailsTable = new DynamoDb.Table( this, 'disposableEmailsTable', {
            partitionKey: {
                name: 'destination',
                type: DynamoDb.AttributeType.STRING,
            },
            sortKey: {
                name: 'messageId',
                type: DynamoDb.AttributeType.STRING,
            },
            billingMode: DynamoDb.BillingMode.PAY_PER_REQUEST,
            removalPolicy: RemovalPolicy.DESTROY,
        } );

        this.disposableReplyAddressesTable = new DynamoDb.Table( this, 'disposableReplyAddressesTable', {
            partitionKey: {
                name: "proxyAddress",
                type: DynamoDb.AttributeType.STRING,
            },
            billingMode: DynamoDb.BillingMode.PAY_PER_REQUEST,
            removalPolicy: RemovalPolicy.DESTROY,
        } );

        this.emailStorageBucket = new S3.Bucket( this, 'emailStorageBucket', {
            removalPolicy: RemovalPolicy.DESTROY,
            blockPublicAccess: S3.BlockPublicAccess.BLOCK_ALL,
        } );

    }
}