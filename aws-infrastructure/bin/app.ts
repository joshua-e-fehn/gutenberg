#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { GutenbergSimplifiedStack } from '../lib/gutenberg-stack-simplified';

const app = new cdk.App();

new GutenbergSimplifiedStack(app, 'GutenbergSimplifiedStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
});
