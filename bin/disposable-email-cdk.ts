#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { DisposableEmailCdkStack } from '../lib/disposable-email-cdk-stack';

const app = new cdk.App();
new DisposableEmailCdkStack(app, 'DisposableEmailCdkStack', {
    env: {
        account: process.env.CDK_DEFAULT_ACCOUNT,
        region: "eu-west-1", // SES Domain is in Ireland
    }
});