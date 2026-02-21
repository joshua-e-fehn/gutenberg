# 🚀 Gutenberg AWS Infrastructure Setup Guide

This guide will help you deploy the Gutenberg audiobook processing pipeline to AWS using CDK.

## Prerequisites

### 1. AWS CLI Setup
```bash
# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Configure AWS credentials
aws configure
# Enter your Access Key ID, Secret Access Key, region (e.g., us-east-1), and output format (json)
```

### 2. Install Node.js and CDK
```bash
# Install Node.js 18+ 
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install AWS CDK globally
npm install -g aws-cdk

# Verify installation
cdk --version
```

### 3. CDK Bootstrap (One-time setup per AWS account/region)
```bash
cdk bootstrap aws://YOUR-ACCOUNT-ID/us-east-1
```

## Quick Start Deployment

### 1. Install Dependencies
```bash
cd aws-infrastructure
npm install
```

### 2. Review and Deploy Infrastructure
```bash
# Preview what will be created
cdk diff

# Deploy the infrastructure
cdk deploy

# This will create:
# - VPC with public/private subnets
# - Aurora PostgreSQL database with RDS Proxy
# - S3 bucket for artifacts
# - Secrets Manager for API keys
# - Lambda functions
# - Step Functions state machine
# - EventBridge daily schedule
```

### 3. Configure API Keys
After deployment, you need to manually set your API keys in Secrets Manager:

```bash
# Get the secret ARNs from CDK output
aws secretsmanager update-secret \
  --secret-id "gutenberg/gemini-api-key" \
  --secret-string '{"apiKey":"YOUR_GEMINI_API_KEY_HERE"}'

aws secretsmanager update-secret \
  --secret-id "gutenberg/elevenlabs-api-key" \
  --secret-string '{"apiKey":"YOUR_ELEVENLABS_API_KEY_HERE"}'
```

### 4. Initialize Database Schema
The database will be automatically created, but you need to run the schema migration:

```bash
# Get database endpoint from CDK output
DB_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name GutenbergPipelineStack \
  --query 'Stacks[0].Outputs[?OutputKey==`DatabaseProxyEndpoint`].OutputValue' \
  --output text)

# Connect and run schema (see database schema section below)
```

## Infrastructure Components

### 🗄️ **Aurora PostgreSQL Database**
- **Type**: Aurora Serverless v2 (cost-optimized)
- **Instance**: t4g.medium (ARM-based, cost-effective)
- **Features**: RDS Proxy for Lambda connection pooling
- **Security**: VPC isolated, IAM authentication

### 🪣 **S3 Storage**
- **Bucket**: `gutenberg-pipeline-{account}-{region}`
- **Structure**:
  - `raw/` - Original scraped content (→ Glacier after 90 days)
  - `parsed/` - Extracted chapters
  - `formatted/` - Gemini-processed text
  - `audio/` - Generated MP3 files

### 🔑 **Secrets Manager**
- `gutenberg/gemini-api-key` - Google Gemini API key
- `gutenberg/elevenlabs-api-key` - ElevenLabs TTS API key
- `gutenberg/database-credentials` - DB admin credentials

### ⚡ **Lambda Functions**
1. **Book Scraper** - Fetches books from Project Gutenberg
2. **Chapter Parser** - Splits books into chapters
3. **Chapter Formatter** - Uses Gemini for audiobook formatting
4. **TTS Generator** - Creates audio using ElevenLabs
5. **Database Manager** - Handles all DB operations

### 🔄 **Step Functions Workflow**
```
Scrape Book → Parse Chapters → Format Chapters (parallel) → Generate Audio (parallel) → Finalize
```

### ⏰ **Scheduled Processing**
- **Trigger**: Daily at 2:00 AM UTC
- **Source**: EventBridge rule
- **Action**: Processes new Project Gutenberg releases

## Cost Estimates (Monthly)

| Service | Usage | Cost |
|---------|-------|------|
| Aurora PostgreSQL | t4g.medium, ~8hrs/day | ~$50 |
| Lambda | 100 books/month | ~$20 |
| S3 Standard | 50GB active storage | ~$1 |
| S3 Glacier | 500GB archived | ~$2 |
| Step Functions | 100 executions | ~$1 |
| Data Transfer | 10GB outbound | ~$1 |
| **Total** | | **~$75/month** |

## Monitoring and Logs

### CloudWatch Logs
- `/aws/lambda/gutenberg-*` - Lambda function logs
- `/aws/stepfunctions/gutenberg-pipeline` - Workflow logs

### CloudWatch Metrics
- Lambda duration, errors, throttles
- Step Functions execution success/failure rates
- Aurora CPU, connections, storage

### Alarms (Recommended)
```bash
# Create alarm for failed Step Functions executions
aws cloudwatch put-metric-alarm \
  --alarm-name "Gutenberg-Pipeline-Failures" \
  --alarm-description "Alert on Step Functions failures" \
  --metric-name "ExecutionsFailed" \
  --namespace "AWS/States" \
  --statistic "Sum" \
  --period 300 \
  --threshold 1 \
  --comparison-operator "GreaterThanOrEqualToThreshold" \
  --evaluation-periods 1
```

## Security Best Practices

### 🔒 **Network Security**
- All Lambda functions in private subnets
- Database in isolated subnets (no internet access)
- RDS Proxy for secure connections

### 🛡️ **IAM Least Privilege**
- Each Lambda has minimal required permissions
- No hardcoded credentials
- All secrets in Secrets Manager

### 🔐 **Data Encryption**
- S3 server-side encryption (SSE-S3)
- Aurora encryption at rest
- Secrets Manager encrypted

## Troubleshooting

### Common Issues

1. **Lambda timeout in VPC**
   - Ensure NAT Gateway is properly configured
   - Check security group rules

2. **Database connection failures**
   - Verify RDS Proxy configuration
   - Check Lambda VPC subnet configuration

3. **API rate limits**
   - Monitor CloudWatch for throttling
   - Adjust Step Functions concurrency limits

### Debug Commands
```bash
# Check Step Functions execution
aws stepfunctions list-executions --state-machine-arn "STEP_FUNCTION_ARN"

# View Lambda logs
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/gutenberg"

# Test database connectivity
aws rds describe-db-proxy-targets --db-proxy-name "GutenbergDBProxy"
```

## Clean Up

To avoid ongoing charges, destroy the infrastructure when not needed:

```bash
# ⚠️ This will delete ALL data!
cdk destroy

# Manually delete:
# - S3 bucket contents (if bucket has objects)
# - CloudWatch log groups (optional)
```

## Next Steps

1. **Deploy the infrastructure** using the commands above
2. **Set up API keys** in Secrets Manager
3. **Run database schema migration** (see database schema section)
4. **Test the pipeline** with a manual Step Functions execution
5. **Monitor** the daily automated runs

---

💡 **Need help?** Check the AWS CloudFormation stack events and Lambda logs for detailed error messages.
