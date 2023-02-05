import { Construct } from "constructs";
import { Duration, RemovalPolicy, Stack } from "aws-cdk-lib";
import * as S3 from "aws-cdk-lib/aws-s3";
import * as Cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as cloudfront_origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as Acm from "aws-cdk-lib/aws-certificatemanager";
import * as Route53 from "aws-cdk-lib/aws-route53";
import * as R53Targets from "aws-cdk-lib/aws-route53-targets";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";

export type StaticWebpageProps = {
    domain: string;
    hostedZone: Route53.IHostedZone;
    staticFilesPath: string;
    stack: Stack;
}

export class StaticWebpage extends Construct {

    readonly siteBucket: S3.Bucket;
    readonly distribution: Cloudfront.Distribution;
    readonly certificate: Acm.Certificate;

    constructor( scope: Construct, id: string, props: StaticWebpageProps ) {
        super( scope, id );

        const cfOai = new Cloudfront.OriginAccessIdentity( this, 'cloudfront-OAI', {
            comment: `OAI for ${ props.domain } Cloudfront distribution`,
        } )

        // create content bucket
        this.siteBucket = new S3.Bucket( this,
            `${ props.domain }-SiteBucket`, {
                bucketName: props.domain + "-frontend",
                publicReadAccess: false,
                blockPublicAccess: S3.BlockPublicAccess.BLOCK_ALL,
                removalPolicy: RemovalPolicy.DESTROY,
                autoDeleteObjects: true,
            } );

        this.siteBucket.grantRead( cfOai );

        // TLS certificate
        this.certificate = new Acm.DnsValidatedCertificate( this,
            `${ props.domain }-Certificate`, {
                domainName: props.domain,
                subjectAlternativeNames: [ "www." + props.domain ],
                hostedZone: props.hostedZone,
                region: 'us-east-1'
            } );

        this.distribution = new Cloudfront.Distribution( this, 'SiteDistribution', {
            certificate: this.certificate,
            defaultRootObject: "index.html",
            domainNames: [ props.domain, "www." + props.domain ],
            minimumProtocolVersion: Cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            errorResponses: [
                {
                    httpStatus: 403,
                    responseHttpStatus: 403,
                    responsePagePath: '/error.html',
                    ttl: Duration.minutes( 30 ),
                }
            ],
            defaultBehavior: {
                origin: new cloudfront_origins.S3Origin( this.siteBucket,
                    { originAccessIdentity: cfOai } ),
                compress: true,
                allowedMethods: Cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
                viewerProtocolPolicy: Cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            }
        } )

        new Route53.ARecord( this, `${ props.domain }-ARecord`, {
            recordName: props.domain,
            target: Route53.RecordTarget.fromAlias(
                new R53Targets.CloudFrontTarget( this.distribution ) ),
            zone: props.hostedZone
        } );

        new Route53.ARecord( this, `${ props.domain }-AAliasRecord`, {
            recordName: "www." + props.domain,
            target: Route53.RecordTarget.fromAlias(
                new R53Targets.CloudFrontTarget( this.distribution ) ),
            zone: props.hostedZone
        } );

        // Deploy site contents to S3 bucket
        new s3deploy.BucketDeployment( this, `${ props.domain }-DeployWithInvalidation`, {
            sources: [ s3deploy.Source.asset( props.staticFilesPath ) ],
            destinationBucket: this.siteBucket,
            distribution: this.distribution,
            distributionPaths: [ '/*' ],
        } );
    }
}