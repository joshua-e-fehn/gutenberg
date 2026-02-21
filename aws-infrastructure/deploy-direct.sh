#!/bin/bash

# Direct CDK bootstrap and deploy with explicit profile handling

set -e

echo "🔐 Setting up AWS credentials..."

# Set environment variables
export AWS_PROFILE=Gutenberg
export CDK_DEFAULT_ACCOUNT=366269158109
export CDK_DEFAULT_REGION=eu-central-1

echo "Profile: $AWS_PROFILE"
echo "Account: $CDK_DEFAULT_ACCOUNT" 
echo "Region: $CDK_DEFAULT_REGION"

echo ""
echo "🏗️ Bootstrapping CDK..."

# Bootstrap with explicit environment
cdk bootstrap aws://366269158109/eu-central-1 --profile Gutenberg

echo ""
echo "🚀 Deploying stack..."

# Deploy with explicit environment  
cdk deploy GutenbergSimplifiedStack \
  --require-approval never \
  --profile Gutenberg

echo ""
echo "✅ Deployment complete!"
