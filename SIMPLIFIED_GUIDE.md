# 🚀 Gutenberg Simplified Pipeline Guide

This guide walks you through deploying and using **only** the scraping, parsing, and formatting steps (no TTS) of your Gutenberg pipeline on AWS.

## 🎯 What This Simplified Pipeline Does

```
📖 Book URL → 🔍 Scrape → 📑 Parse into Chapters → ✨ Format with Gemini → 💾 Store in S3
```

**Components:**
- **Scraper**: Downloads books from Project Gutenberg URLs
- **Parser**: Splits books into individual chapters
- **Formatter**: Uses Gemini AI to optimize text for readability (your enhanced prompt)
- **Database**: Tracks processing status
- **Storage**: S3 buckets for raw, parsed, and formatted content

## 📋 Prerequisites

### 1. Check Your Setup

You already have Node.js v20.12.2 ✅

Now verify AWS CLI:
```bash
aws --version  # Should show AWS CLI 2.x
aws sts get-caller-identity  # Should show your AWS account
```

If you need to install/configure AWS CLI:
```bash
# macOS
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /

# Configure credentials
aws configure
# Enter your AWS Access Key ID
# Enter your AWS Secret Access Key
# Default region: us-east-1 (recommended)
# Default output format: json
```

## 🚀 Step 1: Deploy Infrastructure

Run the simplified deployment script:

```bash
cd aws-infrastructure
./deploy-simplified.sh
```

This will:
- Install CDK dependencies
- Bootstrap CDK (one-time setup)
- Create Lambda function templates with your enhanced prompts
- Deploy all AWS infrastructure
- Show you the next steps

**Expected deployment time:** 8-12 minutes

**What gets created:**
- VPC with public/private subnets
- Aurora PostgreSQL database
- S3 bucket for content storage
- 4 Lambda functions (scraper, parser, formatter, database)
- Step Functions workflow
- Secrets Manager for API keys

## 🔑 Step 2: Configure API Key

After deployment, set your Gemini API key:

```bash
# Replace YOUR_API_KEY with your actual Gemini API key
aws secretsmanager update-secret \
  --secret-id "gutenberg/gemini-api-key" \
  --secret-string '{"apiKey":"YOUR_API_KEY"}'
```

## 🗄️ Step 3: Initialize Database

The deployment will show you the database endpoint. Connect and apply the schema:

```bash
# Replace <DB_ENDPOINT> with the actual endpoint from deployment output
psql -h <DB_ENDPOINT> -U gutenberg_admin -d gutenberg_pipeline -f database-schema.sql
```

You'll be prompted for the database password (it's in AWS Secrets Manager).

## 🧪 Step 4: Test the Pipeline

Test with a classic book from Project Gutenberg:

```bash
# Replace <STATE_MACHINE_ARN> with the actual ARN from deployment output
aws stepfunctions start-execution \
  --state-machine-arn "<STATE_MACHINE_ARN>" \
  --input '{
    "bookId": "alice-in-wonderland",
    "sourceUrl": "https://www.gutenberg.org/files/11/11-0.txt"
  }'
```

## 📊 Step 5: Monitor Progress

### Check Execution Status
```bash
# List recent executions
aws stepfunctions list-executions --state-machine-arn "<STATE_MACHINE_ARN>" --max-items 5

# Get detailed execution info
aws stepfunctions describe-execution --execution-arn "<EXECUTION_ARN>"
```

### View CloudWatch Logs
```bash
# Scraper logs
aws logs tail /aws/lambda/GutenbergSimplifiedStack-BookScraper --follow

# Formatter logs  
aws logs tail /aws/lambda/GutenbergSimplifiedStack-BookFormatter --follow

# Parser logs
aws logs tail /aws/lambda/GutenbergSimplifiedStack-BookParser --follow
```

### Check S3 Content
After successful processing, you'll see this structure:
```
your-bucket/
├── raw/2025-08-22/alice-in-wonderland/book.txt
├── parsed/alice-in-wonderland/
│   ├── chapter_001.txt
│   ├── chapter_002.txt
│   └── ...
└── formatted/alice-in-wonderland/
    ├── chapter_001.txt
    ├── chapter_002.txt
    └── ...
```

### Query Database
```sql
-- Connect to your database and check status
SELECT * FROM book_processing_overview WHERE book_id = 'alice-in-wonderland';

-- View processing logs
SELECT * FROM processing_logs WHERE book_id = 'alice-in-wonderland' ORDER BY created_at;
```

## 🔧 Step 6: Customize for Your Needs

### Test Different Books
```bash
# Test with different Project Gutenberg books
aws stepfunctions start-execution \
  --state-machine-arn "<STATE_MACHINE_ARN>" \
  --input '{
    "bookId": "pride-and-prejudice",
    "sourceUrl": "https://www.gutenberg.org/files/1342/1342-0.txt"
  }'
```

### Modify Processing Logic

The Lambda functions are now templates. You can enhance them:

1. **Scraper** (`lambda-functions/scraper/index.py`):
   - Add RSS feed parsing
   - Handle different file formats
   - Add metadata extraction

2. **Parser** (`lambda-functions/parser/index.py`):
   - Improve chapter detection
   - Handle different book structures
   - Add chapter metadata

3. **Formatter** (`lambda-functions/formatter/index.py`):
   - Already has your enhanced Gemini prompt
   - Adjust token limits or model parameters
   - Add genre-specific formatting

4. **Database** (`lambda-functions/database/index.py`):
   - Add more detailed tracking
   - Create custom reports
   - Add notification logic

After modifying Lambda functions:
```bash
cd aws-infrastructure
cdk deploy GutenbergSimplifiedStack  # Redeploy with changes
```

## 💰 Cost Estimation

**Expected monthly costs for moderate usage (10-20 books):**
- Aurora PostgreSQL: ~$40-50
- Lambda executions: ~$5-10
- S3 storage: ~$1-3
- Gemini API calls: ~$5-15
- **Total: ~$50-75/month**

## 🔍 Troubleshooting

### Common Issues

1. **Lambda timeout in VPC**
   - Check NAT Gateway is working
   - Verify security group allows outbound traffic

2. **Gemini API errors**
   - Verify API key is set correctly
   - Check token limits (currently 7000)
   - Monitor rate limiting

3. **Database connection issues**
   - Check RDS security group allows Lambda access
   - Verify database credentials in Secrets Manager

4. **Chapter parsing issues**
   - Review parser logic for your specific book formats
   - Adjust chapter detection patterns

### Debug Commands

```bash
# Check specific execution details
aws stepfunctions get-execution-history --execution-arn "<EXECUTION_ARN>"

# View Lambda function configuration
aws lambda get-function --function-name GutenbergSimplifiedStack-BookFormatter

# Test Lambda function directly
aws lambda invoke \
  --function-name GutenbergSimplifiedStack-BookScraper \
  --payload '{"bookId":"test","sourceUrl":"https://www.gutenberg.org/files/11/11-0.txt"}' \
  response.json
```

## 🎯 Success Criteria

After following this guide, you should have:

✅ **Infrastructure deployed** - All AWS resources created  
✅ **API key configured** - Gemini API accessible  
✅ **Database initialized** - Schema applied and accessible  
✅ **Test execution completed** - Book processed through all steps  
✅ **Content in S3** - Raw, parsed, and formatted files stored  
✅ **Database tracking** - Processing status recorded  

## 🔄 Next Steps

Once this simplified pipeline is working:

1. **Add automation**: Enable EventBridge schedule for daily runs
2. **Scale up**: Process multiple books concurrently
3. **Add TTS**: Integrate ElevenLabs for audio generation
4. **Enhance parsing**: Improve chapter detection algorithms
5. **Add monitoring**: Set up CloudWatch alarms and dashboards

## 🆘 Need Help?

If you encounter issues:

1. Check CloudWatch logs for detailed error messages
2. Verify all prerequisites are met
3. Ensure your AWS credentials have sufficient permissions
4. Review the Step Functions execution history for failed steps

The simplified pipeline focuses on the core text processing workflow, making it easier to debug and understand before adding complexity like TTS generation.
