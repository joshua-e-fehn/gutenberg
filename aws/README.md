# `aws/` - AWS CDK Source Of Truth

This directory is the single CDK project for AWS infrastructure in this repository.

## Scope

- CDK app entrypoint: `aws/bin/gutenberg-cdk.ts`
- Stack definition: `aws/lib/gutenberg-cdk-stack.ts` (`BackendStack`)
- Lambda source code packaged by CDK: `aws/lambda/*`
- SQL schema used by the project: `aws/database-schema.sql`

## Prerequisites

- [Install Bun](https://bun.sh/docs/installation)
- AWS credentials configured for the target account/region

## Setup

```bash
cd aws
bun install
```

## Common Commands

```bash
# List stacks
bun run cdk list

# Synthesize CloudFormation template
bun run cdk synth

# Preview changes
bun run cdk diff

# Deploy
bun run cdk deploy
```
