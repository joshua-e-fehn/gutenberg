#!/bin/bash

# Gutenberg AWS Infrastructure Deployment Script
# This script automates the complete setup of the Gutenberg audiobook pipeline

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
STACK_NAME="GutenbergPipelineStack"

echo -e "${BLUE}🚀 Gutenberg AWS Infrastructure Deployment${NC}"
echo "======================================================"

# Check prerequisites
echo -e "${YELLOW}📋 Checking prerequisites...${NC}"

if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI not installed. Please install AWS CLI v2.${NC}"
    exit 1
fi

if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js not installed. Please install Node.js 18+.${NC}"
    exit 1
fi

if ! command -v cdk &> /dev/null; then
    echo -e "${RED}❌ AWS CDK not installed. Installing now...${NC}"
    npm install -g aws-cdk
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ AWS credentials not configured. Please run 'aws configure'.${NC}"
    exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "${GREEN}✅ AWS Account: ${AWS_ACCOUNT_ID}${NC}"
echo -e "${GREEN}✅ AWS Region: ${AWS_REGION}${NC}"

# CDK Bootstrap check
echo -e "${YELLOW}🔧 Checking CDK bootstrap...${NC}"
if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region $AWS_REGION &> /dev/null; then
    echo -e "${YELLOW}⚡ Bootstrapping CDK for account ${AWS_ACCOUNT_ID} in ${AWS_REGION}...${NC}"
    cdk bootstrap aws://${AWS_ACCOUNT_ID}/${AWS_REGION}
else
    echo -e "${GREEN}✅ CDK already bootstrapped${NC}"
fi

# Install dependencies
echo -e "${YELLOW}📦 Installing Node.js dependencies...${NC}"
cd aws-infrastructure
npm install

# Synthesize CloudFormation template
echo -e "${YELLOW}🔍 Synthesizing CloudFormation template...${NC}"
cdk synth

# Deploy infrastructure
echo -e "${YELLOW}🚀 Deploying infrastructure stack...${NC}"
echo "This will create:"
echo "  • VPC with public/private subnets"
echo "  • Aurora PostgreSQL database with RDS Proxy"
echo "  • S3 bucket for pipeline artifacts"
echo "  • Secrets Manager for API keys"
echo "  • Lambda functions"
echo "  • Step Functions state machine"
echo "  • EventBridge daily schedule"
echo ""

read -p "Continue with deployment? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

echo -e "${BLUE}⏳ Deploying (this may take 10-15 minutes)...${NC}"
cdk deploy --require-approval never

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Infrastructure deployed successfully!${NC}"
else
    echo -e "${RED}❌ Deployment failed!${NC}"
    exit 1
fi

# Get outputs
echo -e "${YELLOW}📊 Getting deployment outputs...${NC}"
S3_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`S3BucketName`].OutputValue' \
    --output text)

DB_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`DatabaseProxyEndpoint`].OutputValue' \
    --output text)

GEMINI_SECRET_ARN=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`GeminiSecretArn`].OutputValue' \
    --output text)

ELEVENLABS_SECRET_ARN=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`ElevenLabsSecretArn`].OutputValue' \
    --output text)

STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`StateMachineArn`].OutputValue' \
    --output text)

echo ""
echo "🎉 Deployment Complete!"
echo "======================"
echo -e "${GREEN}S3 Bucket:${NC} $S3_BUCKET"
echo -e "${GREEN}Database Endpoint:${NC} $DB_ENDPOINT"
echo -e "${GREEN}State Machine ARN:${NC} $STATE_MACHINE_ARN"
echo ""

# API Key setup instructions
echo -e "${YELLOW}🔑 Next Steps - Configure API Keys:${NC}"
echo ""
echo "1. Set your Gemini API key:"
echo "   aws secretsmanager update-secret \\"
echo "     --secret-id \"$GEMINI_SECRET_ARN\" \\"
echo "     --secret-string '{\"apiKey\":\"YOUR_GEMINI_API_KEY_HERE\"}'"
echo ""
echo "2. Set your ElevenLabs API key:"
echo "   aws secretsmanager update-secret \\"
echo "     --secret-id \"$ELEVENLABS_SECRET_ARN\" \\"
echo "     --secret-string '{\"apiKey\":\"YOUR_ELEVENLABS_API_KEY_HERE\"}'"
echo ""

# Database setup instructions
echo -e "${YELLOW}🗄️ Database Setup:${NC}"
echo ""
echo "3. Initialize database schema:"
echo "   The database is ready, but you need to apply the schema."
echo "   Connect using the RDS Proxy endpoint: $DB_ENDPOINT"
echo ""
echo "   You can use the database-schema.sql file to create the tables."
echo ""

# Test instructions
echo -e "${YELLOW}🧪 Testing:${NC}"
echo ""
echo "4. Test the pipeline:"
echo "   aws stepfunctions start-execution \\"
echo "     --state-machine-arn \"$STATE_MACHINE_ARN\" \\"
echo "     --input '{
      \"bookId\": \"test-book-001\",
      \"sourceUrl\": \"https://www.gutenberg.org/ebooks/11.txt.utf-8\",
      \"scrapeOptions\": {\"force\": false},
      \"formatOptions\": {\"model\": \"gemini-2.0-flash-exp\"},
      \"ttsOptions\": {\"voiceId\": \"Rachel\", \"format\": \"mp3\"}
    }'"
echo ""

# Cost monitoring warning
echo -e "${YELLOW}⚠️  Cost Monitoring:${NC}"
echo "   Estimated monthly cost: ~$75"
echo "   - Aurora PostgreSQL: ~$50"
echo "   - Lambda executions: ~$20"
echo "   - S3 storage: ~$3"
echo "   - Other services: ~$2"
echo ""
echo "   Set up billing alerts in AWS Console!"
echo ""

# Cleanup instructions
echo -e "${YELLOW}🧹 To clean up later:${NC}"
echo "   cdk destroy"
echo "   (This will delete all infrastructure but preserve S3 data)"
echo ""

echo -e "${GREEN}🎯 Setup complete! Your Gutenberg audiobook pipeline is ready.${NC}"
