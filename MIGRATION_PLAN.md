# 📋 Gutenberg to AWS Migration Plan

This document outlines the step-by-step process to migrate your Gutenberg audiobook pipeline from local execution to AWS cloud infrastructure.

## 🎯 Migration Overview

### Current State → Target State

| Component | Current | Target AWS Service |
|-----------|---------|-------------------|
| Book Scraper | `scripts/scraper/bookScraper.py` | Lambda + S3 |
| Text Formatter | `scripts/audioBookFormatter.py` | Lambda + Gemini API |
| Local Storage | `books/` directory | S3 buckets |
| Manual Execution | Command line | Step Functions + EventBridge |
| No Database | File-based | Aurora PostgreSQL |
| Local Scheduling | Cron | EventBridge Rules |

## 🚀 Phase 1: Infrastructure Setup

### Step 1: AWS Prerequisites

**You need to do this manually:**

1. **Install AWS CLI v2**:
   ```bash
   # macOS
   curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
   sudo installer -pkg AWSCLIV2.pkg -target /
   
   # Verify
   aws --version
   ```

2. **Configure AWS Credentials**:
   ```bash
   aws configure
   # Enter your AWS Access Key ID
   # Enter your AWS Secret Access Key  
   # Default region: us-east-1
   # Default output format: json
   ```

3. **Install Node.js 18+**:
   ```bash
   # macOS with Homebrew
   brew install node
   
   # Verify
   node --version  # Should be 18+
   ```

4. **Install AWS CDK**:
   ```bash
   npm install -g aws-cdk
   cdk --version
   ```

### Step 2: Deploy Infrastructure

**Run the automated deployment:**

```bash
cd aws-infrastructure
./deploy.sh
```

This script will:
- ✅ Check all prerequisites
- ✅ Bootstrap CDK (one-time setup)
- ✅ Deploy all AWS infrastructure
- ✅ Provide setup instructions for next steps

**Expected deployment time:** 10-15 minutes

**Infrastructure created:**
- VPC with public/private subnets
- Aurora PostgreSQL database (with RDS Proxy)
- S3 bucket for storage
- Secrets Manager for API keys
- 5 Lambda functions
- Step Functions state machine
- EventBridge daily schedule

### Step 3: Configure API Keys

**After deployment, set your API keys:**

```bash
# Replace with your actual API keys
aws secretsmanager update-secret \
  --secret-id "gutenberg/gemini-api-key" \
  --secret-string '{"apiKey":"YOUR_GEMINI_API_KEY"}'

aws secretsmanager update-secret \
  --secret-id "gutenberg/elevenlabs-api-key" \
  --secret-string '{"apiKey":"YOUR_ELEVENLABS_API_KEY"}'
```

### Step 4: Initialize Database

**Apply the database schema:**

```bash
# Get database endpoint from deployment output
DB_ENDPOINT="your-rds-proxy-endpoint"

# Connect and apply schema
psql -h $DB_ENDPOINT -U gutenberg_admin -d gutenberg_pipeline -f database-schema.sql
```

## 🔄 Phase 2: Code Migration

### Current Code → Lambda Functions

I've created the framework for migrating your existing code:

| Your Current File | Target Lambda | Status |
|------------------|---------------|---------|
| `scripts/scraper/bookScraper.py` | `lambda-functions/scraper/` | 🟡 Template ready |
| `scripts/audioBookFormatter.py` | `lambda-functions/formatter/` | 🟡 Template ready |
| New: Chapter Parser | `lambda-functions/parser/` | 🟡 Template ready |
| New: TTS Generator | `lambda-functions/tts/` | 🟡 Template ready |
| New: Database Manager | `lambda-functions/database/` | 🟡 Template ready |

### Step 5: Complete Lambda Functions

**You need to complete these implementations:**

1. **Scraper Lambda** (`lambda-functions/scraper/index.py`):
   - Migrate RSS parsing logic from `bookScraper.py`
   - Add S3 upload functionality
   - Add database status updates

2. **Parser Lambda** (`lambda-functions/parser/index.py`):
   - Extract chapter splitting logic
   - Parse books into individual chapters
   - Store chapter metadata in database

3. **Formatter Lambda** (`lambda-functions/formatter/index.py`):
   - ✅ Already has your enhanced prompt
   - ✅ Gemini API integration ready
   - Add database status tracking

4. **TTS Lambda** (`lambda-functions/tts/index.py`):
   - Integrate ElevenLabs API
   - Stream audio directly to S3
   - Handle large file uploads

5. **Database Lambda** (`lambda-functions/database/index.py`):
   - Book/chapter status management
   - Processing logs
   - Status queries

### Step 6: Deploy Lambda Code

```bash
# After completing the Lambda functions
cd aws-infrastructure
cdk deploy  # Redeploy with updated Lambda code
```

## 🧪 Phase 3: Testing & Validation

### Step 7: Test Individual Components

```bash
# Test the complete pipeline
aws stepfunctions start-execution \
  --state-machine-arn "YOUR_STATE_MACHINE_ARN" \
  --input '{
    "bookId": "test-book-001",
    "sourceUrl": "https://www.gutenberg.org/ebooks/11.txt.utf-8",
    "scrapeOptions": {"force": false},
    "formatOptions": {"model": "gemini-2.0-flash-exp"},
    "ttsOptions": {"voiceId": "Rachel", "format": "mp3"}
  }'
```

### Step 8: Validate Results

1. **Check S3 bucket structure**:
   ```
   your-bucket/
   ├── raw/2025-08-21/test-book-001/book.txt
   ├── parsed/test-book-001/chapter_001.txt
   ├── formatted/test-book-001/chapter_001.txt
   └── audio/test-book-001/chapter_001.mp3
   ```

2. **Verify database entries**:
   ```sql
   SELECT * FROM book_processing_overview WHERE book_id = 'test-book-001';
   ```

3. **Check CloudWatch logs** for any errors

## 📊 Phase 4: Production Readiness

### Step 9: Monitoring Setup

1. **CloudWatch Alarms**:
   ```bash
   # Set up failure alerts
   aws cloudwatch put-metric-alarm \
     --alarm-name "Gutenberg-Pipeline-Failures" \
     --alarm-description "Alert on Step Functions failures" \
     --metric-name "ExecutionsFailed" \
     --namespace "AWS/States" \
     --statistic "Sum" \
     --period 300 \
     --threshold 1 \
     --comparison-operator "GreaterThanOrEqualToThreshold"
   ```

2. **Cost Monitoring**:
   - Set up AWS Budgets for $100/month threshold
   - Enable detailed billing

### Step 10: Data Migration (Optional)

**Migrate existing processed books:**

```bash
# Upload existing books to S3
aws s3 sync books/ s3://your-bucket/migrated-books/ \
  --exclude "*.wav" \
  --exclude "*.mp3"

# Import book metadata to database
# (You'll need to create a migration script)
```

## 🔄 Phase 5: Cutover

### Step 11: Switch from Local to Cloud

1. **Disable local cron job**:
   ```bash
   crontab -e
   # Comment out the Gutenberg line
   ```

2. **Enable AWS EventBridge schedule**:
   - The daily schedule is already created by CDK
   - It will run at 2:00 AM UTC daily

3. **Monitor first automated run**:
   ```bash
   # Check execution status
   aws stepfunctions list-executions \
     --state-machine-arn "YOUR_STATE_MACHINE_ARN" \
     --max-items 5
   ```

## 💰 Cost Management

### Expected Monthly Costs

| Service | Usage | Cost |
|---------|-------|------|
| Aurora PostgreSQL | t4g.medium, 8hrs/day | ~$50 |
| Lambda | 100 books/month | ~$20 |
| S3 Standard | 50GB active | ~$1 |
| S3 Glacier | 500GB archived | ~$2 |
| Step Functions | 100 executions | ~$1 |
| **Total** | | **~$75/month** |

### Cost Optimization Tips

1. **Aurora**: Consider Aurora Serverless v2 for variable workloads
2. **S3**: Lifecycle rules automatically move old data to cheaper storage
3. **Lambda**: Right-size memory allocations after testing
4. **RDS Proxy**: Reduces connection overhead

## 🚨 Troubleshooting Guide

### Common Issues

1. **Lambda timeout in VPC**:
   - Check NAT Gateway configuration
   - Verify security group rules

2. **Database connection failures**:
   - Confirm RDS Proxy setup
   - Check Lambda VPC configuration

3. **API rate limits**:
   - Monitor CloudWatch for throttling
   - Adjust Step Functions concurrency

4. **S3 access denied**:
   - Verify IAM permissions
   - Check bucket policies

### Debug Commands

```bash
# Check Step Functions execution
aws stepfunctions describe-execution --execution-arn "EXECUTION_ARN"

# View Lambda logs
aws logs tail /aws/lambda/gutenberg-book-scraper --follow

# Test database connection
aws rds describe-db-proxy-targets --db-proxy-name "GutenbergDBProxy"
```

## 🎉 Success Criteria

### Phase 1 Complete ✅
- [ ] AWS infrastructure deployed
- [ ] API keys configured
- [ ] Database schema applied

### Phase 2 Complete ✅
- [ ] All Lambda functions implemented
- [ ] Code deployed successfully
- [ ] Unit tests passing

### Phase 3 Complete ✅
- [ ] End-to-end test successful
- [ ] Data flowing through pipeline
- [ ] Audio files generated

### Phase 4 Complete ✅
- [ ] Monitoring enabled
- [ ] Alerts configured
- [ ] Cost tracking active

### Phase 5 Complete ✅
- [ ] Daily automation working
- [ ] Local system decommissioned
- [ ] Cloud pipeline operational

---

## 📞 Next Steps

1. **Run the deployment script**: `./aws-infrastructure/deploy.sh`
2. **Configure your API keys** as shown above
3. **Complete the Lambda function implementations**
4. **Test the pipeline** with a sample book
5. **Monitor and optimize** based on actual usage

The infrastructure is ready to deploy! Let me know when you're ready to proceed with any specific phase.
