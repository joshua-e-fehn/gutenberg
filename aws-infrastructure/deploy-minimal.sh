#!/bin/bash

# Gutenberg Minimal Deployment Script
# Simple deployment # Create Lambda function directories and files
echo -e "${BLUE}📁 Setting up Lambda function directories...${NC}"

mkdir -p ../lambda-functions/scraper
mkdir -p ../lambda-functions/parser
mkdir -p ../lambda-functions/formatter

# Deploy the stack
echo -e "${BLUE}🚀 Deploying simplified infrastructure...${NC}"
cdk deploy GutenbergSimplifiedStack --require-approval never

echo -e "${GREEN}🎉 Deployment completed successfully!${NC}"
echo ""
echo -e "${BLUE}📋 Next steps:${NC}"
echo "1. Set your Gemini API key:"
echo "   aws secretsmanager update-secret --secret-id 'gutenberg/gemini-api-key' --secret-string '{\"apiKey\":\"YOUR_API_KEY\"}' --profile Gutenberg"
echo ""
echo "2. Test the pipeline:"
echo "   aws stepfunctions start-execution --state-machine-arn <STATE_MACHINE_ARN> --input '{\"bookId\":\"test-book\",\"sourceUrl\":\"https://www.gutenberg.org/files/11/11-0.txt\"}' --profile Gutenberg"
echo ""
echo -e "${YELLOW}💡 Stack outputs are shown above with all the ARNs you need!${NC}"raping, parsing, and formatting (no database, no TTS)

set -e

echo "🚀 Gutenberg Minimal Deployment (Scrape + Parse + Format)"
echo "========================================================"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Set AWS profile
export AWS_PROFILE=Gutenberg

# Check prerequisites
echo -e "${BLUE}🔍 Checking prerequisites...${NC}"

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI not found. Please install AWS CLI v2.${NC}"
    exit 1
fi

# Check AWS credentials with profile
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ AWS credentials not working with profile Gutenberg.${NC}"
    echo "Run: aws sso login --profile Gutenberg"
    exit 1
fi

# Check Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js not found. Please install Node.js 18+.${NC}"
    exit 1
fi

# Check CDK
if ! command -v cdk &> /dev/null; then
    echo -e "${YELLOW}⚠️ AWS CDK not found. Installing...${NC}"
    npm install -g aws-cdk
fi

echo -e "${GREEN}✅ All prerequisites met!${NC}"

# Get AWS account info
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region)

echo -e "${BLUE}📋 Deployment details:${NC}"
echo "Account ID: $ACCOUNT_ID"
echo "Region: $REGION"
echo "Stack: GutenbergSimplifiedStack"
echo "Profile: $AWS_PROFILE"

# Navigate to infrastructure directory
cd "$(dirname "$0")"

# Install dependencies
echo -e "${BLUE}� Installing CDK dependencies...${NC}"
npm install

# Bootstrap CDK (one-time setup)
echo -e "${BLUE}�️ Bootstrapping CDK...${NC}"
cdk bootstrap

# Create Lambda function directories and files
echo -e "${BLUE}� Setting up Lambda function directories...${NC}"

mkdir -p ../lambda-functions/scraper
mkdir -p ../lambda-functions/parser
mkdir -p ../lambda-functions/formatter
