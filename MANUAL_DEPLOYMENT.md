# 🚀 Manual Deployment Steps

Since we're having authentication issues with the automated script, let's deploy step by step:

## Step 1: Re-authenticate with AWS
```bash
aws sso login --profile Gutenberg
```

## Step 2: Verify authentication
```bash
AWS_PROFILE=Gutenberg aws sts get-caller-identity
```

## Step 3: Set environment variables
```bash
export AWS_PROFILE=Gutenberg
export CDK_DEFAULT_ACCOUNT=366269158109
export CDK_DEFAULT_REGION=eu-central-1
```

## Step 4: Navigate to infrastructure directory
```bash
cd aws-infrastructure
```

## Step 5: Install dependencies (if not done)
```bash
npm install
```

## Step 6: Bootstrap CDK
```bash
cdk bootstrap --profile Gutenberg
```

## Step 7: Deploy the stack
```bash
cdk deploy GutenbergSimplifiedStack --require-approval never --profile Gutenberg
```

## What will be created:
- S3 bucket: `gutenberg-content-366269158109-eu-central-1`
- 3 Lambda functions: BookScraper, BookParser, BookFormatter
- Step Functions state machine for workflow
- Secrets Manager for Gemini API key
- IAM roles and policies

## After deployment:
1. Set your Gemini API key:
```bash
aws secretsmanager update-secret \
  --secret-id 'gutenberg/gemini-api-key' \
  --secret-string '{"apiKey":"YOUR_GEMINI_API_KEY"}' \
  --profile Gutenberg
```

2. Test the pipeline:
```bash
aws stepfunctions start-execution \
  --state-machine-arn "arn:aws:states:eu-central-1:366269158109:stateMachine:GutenbergProcessingPipeline" \
  --input '{"bookId":"test-book","sourceUrl":"https://www.gutenberg.org/files/11/11-0.txt"}' \
  --profile Gutenberg
```

Try these steps one by one and let me know if any fail!
