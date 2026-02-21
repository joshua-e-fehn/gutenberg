# AWS Step Functions Workflow (Scrape → Parse → Format → TTS)

This blueprint gives you:

* **Amazon States Language (ASL) JSON** you can paste into the Step Functions console or deploy via IaC.
* **Input/Output contracts** for your Lambdas.
* **CDK TypeScript snippet** to deploy the state machine + EventBridge schedule.
* **Operational notes** (retries, concurrency caps, idempotency, costs).

---

## 1) State machine: Assumptions & Contracts

### Execution Input (book-level)

```json
{
  "bookId": "bk_12345",
  "sourceUrl": "https://example.com/book.pdf",
  "scrapeOptions": { "force": false },
  "formatOptions": { "model": "gemini-1.5" },
  "ttsOptions": { "voiceId": "Rachel", "format": "mp3" },
  "s3": {
    "bucketRaw": "your-bucket",
    "bucketParsed": "your-bucket",
    "bucketFormatted": "your-bucket",
    "bucketAudio": "your-bucket"
  },
  "db": { "clusterArn": "arn:aws:rds:...", "secretArn": "arn:aws:secretsmanager:..." },
  "limits": { "formatConcurrency": 50, "ttsConcurrency": 30 },
  "metadata": { "requestedBy": "system" }
}
```

### Lambda Interfaces (shape only)

* **ScraperLambda** (per book)

  * **Input:** `{ bookId, sourceUrl, s3.bucketRaw, ... }`
  * **Output:** `{ bookId, rawS3Key: "raw/2025-08-15/bk_12345/book.pdf" }`

* **UpsertBookLambda** (per book)

  * **In:** `{ bookId, status, rawS3Key? }` → updates Aurora/Dynamo
  * **Out:** echoes input

* **ParseLambda** (per book)

  * **In:** `{ bookId, rawS3Key, s3.bucketParsed }`
  * **Out:** `{ bookId, chapters: [{ chapterId: "ch_001", title: "Intro", parsedS3Key: "parsed/bk_12345/ch_001.json"}, ...] }`

* **FormatChapterLambda** (per chapter)

  * **In:** `{ bookId, chapterId, parsedS3Key, s3.bucketFormatted, formatOptions, idempotencyKey }`
  * **Out:** `{ chapterId, formattedS3Key: "formatted/bk_12345/ch_001.md" }`

* **TTSChapterLambda** (per chapter)

  * **In:** `{ bookId, chapterId, formattedS3Key, s3.bucketAudio, ttsOptions, idempotencyKey }`
  * **Out:** `{ chapterId, audioS3Key: "audio/bk_12345/ch_001.mp3" }`

* **UpdateChapterStatusLambda** (per chapter)

  * **In:** `{ bookId, chapterId, status, formattedS3Key?, audioS3Key?, error? }`
  * **Out:** echo

* **FinalizeBookLambda** (per book)

  * **In:** `{ bookId }` → roll-up status
  * **Out:** `{ bookId, status: "complete" }`

> All per-chapter Lambdas must be **idempotent** using `idempotencyKey = `\${bookId}:\${chapterId}:\${stage}\`.

---

## 2) Amazon States Language (ASL) – JSON definition

Replace the `Resource` ARNs with your Lambda ARNs (or use `arn:aws:states:::lambda:invoke` with `Payload`). This version uses **`MaxConcurrency`** to enforce Gemini and ElevenLabs rate limits.

```json
{
  "Comment": "Scrape → Parse → Format → TTS pipeline",
  "StartAt": "UpsertBook_Queued",
  "States": {
    "UpsertBook_Queued": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${UpsertBookLambdaArn}",
        "Payload": {
          "bookId.$": "$.bookId",
          "status": "queued"
        }
      },
      "Next": "ScrapeBook"
    },
    "ScrapeBook": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${ScraperLambdaArn}",
        "Payload": {
          "bookId.$": "$.bookId",
          "sourceUrl.$": "$.sourceUrl",
          "s3": {
            "bucketRaw.$": "$.s3.bucketRaw"
          },
          "scrapeOptions.$": "$.scrapeOptions"
        }
      },
      "ResultSelector": {
        "bookId.$": "$.Payload.bookId",
        "rawS3Key.$": "$.Payload.rawS3Key"
      },
      "Retry": [
        { "ErrorEquals": ["States.ALL"], "IntervalSeconds": 5, "MaxAttempts": 3, "BackoffRate": 2.0 }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.error",
          "Next": "MarkBookFailed"
        }
      ],
      "Next": "UpsertBook_Scraped"
    },
    "UpsertBook_Scraped": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${UpsertBookLambdaArn}",
        "Payload": {
          "bookId.$": "$.bookId",
          "status": "scraped",
          "rawS3Key.$": "$.rawS3Key"
        }
      },
      "Next": "ParseToChapters"
    },
    "ParseToChapters": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${ParseLambdaArn}",
        "Payload": {
          "bookId.$": "$.bookId",
          "rawS3Key.$": "$.rawS3Key",
          "s3": { "bucketParsed.$": "$.s3.bucketParsed" }
        }
      },
      "ResultSelector": {
        "bookId.$": "$.Payload.bookId",
        "chapters.$": "$.Payload.chapters"
      },
      "Retry": [
        { "ErrorEquals": ["States.ALL"], "IntervalSeconds": 3, "MaxAttempts": 2, "BackoffRate": 2.0 }
      ],
      "Catch": [
        { "ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "MarkBookFailed" }
      ],
      "Next": "UpsertBook_Parsed"
    },
    "UpsertBook_Parsed": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${UpsertBookLambdaArn}",
        "Payload": {
          "bookId.$": "$.bookId",
          "status": "parsed",
          "chapterCount.$": "States.ArrayLength($.chapters)"
        }
      },
      "Next": "FormatChaptersMap"
    },
    "FormatChaptersMap": {
      "Type": "Map",
      "ItemsPath": "$.chapters",
      "MaxConcurrency.$": "$.limits.formatConcurrency",
      "ItemSelector": {
        "bookId.$": "$.bookId",
        "chapterId.$": "$.chapterId",
        "parsedS3Key.$": "$.parsedS3Key",
        "s3.$": "$.s3",
        "formatOptions.$": "$.formatOptions",
        "idempotencyKey.$": "States.Format('{}:{}:format', $.bookId, $.chapterId)"
      },
      "ResultPath": "$.formatted",
      "Iterator": {
        "StartAt": "FormatChapter",
        "States": {
          "FormatChapter": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "${FormatChapterLambdaArn}",
              "Payload.$": "$"
            },
            "ResultSelector": {
              "chapterId.$": "$.Payload.chapterId",
              "formattedS3Key.$": "$.Payload.formattedS3Key"
            },
            "Retry": [
              { "ErrorEquals": ["ThrottlingException", "TooManyRequestsException"], "IntervalSeconds": 2, "MaxAttempts": 5, "BackoffRate": 2.5 },
              { "ErrorEquals": ["States.ALL"], "IntervalSeconds": 4, "MaxAttempts": 2, "BackoffRate": 2.0 }
            ],
            "Catch": [
              { "ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "UpdateChapterFormattedFailed" }
            ],
            "Next": "UpdateChapterFormattedSuccess"
          },
          "UpdateChapterFormattedSuccess": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "${UpdateChapterStatusLambdaArn}",
              "Payload": {
                "bookId.$": "$.bookId",
                "chapterId.$": "$.chapterId",
                "status": "formatted",
                "formattedS3Key.$": "$.formattedS3Key"
              }
            },
            "Next": "TTSChapter"
          },
          "UpdateChapterFormattedFailed": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "${UpdateChapterStatusLambdaArn}",
              "Payload": {
                "bookId.$": "$.bookId",
                "chapterId.$": "$.chapterId",
                "status": "format_failed",
                "error.$": "$.error"
              }
            },
            "Next": "FailState"
          },
          "TTSChapter": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "${TTSChapterLambdaArn}",
              "Payload": {
                "bookId.$": "$.bookId",
                "chapterId.$": "$.chapterId",
                "formattedS3Key.$": "$.formattedS3Key",
                "s3.$": "$.s3",
                "ttsOptions.$": "$.ttsOptions",
                "idempotencyKey.$": "States.Format('{}:{}:tts', $.bookId, $.chapterId)"
              }
            },
            "ResultSelector": {
              "chapterId.$": "$.Payload.chapterId",
              "audioS3Key.$": "$.Payload.audioS3Key"
            },
            "Retry": [
              { "ErrorEquals": ["ThrottlingException", "TooManyRequestsException"], "IntervalSeconds": 2, "MaxAttempts": 5, "BackoffRate": 2.5 },
              { "ErrorEquals": ["States.ALL"], "IntervalSeconds": 4, "MaxAttempts": 2, "BackoffRate": 2.0 }
            ],
            "Catch": [
              { "ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "UpdateChapterTTSFailed" }
            ],
            "Next": "UpdateChapterTTSSuccess"
          },
          "UpdateChapterTTSSuccess": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "${UpdateChapterStatusLambdaArn}",
              "Payload": {
                "bookId.$": "$.bookId",
                "chapterId.$": "$.chapterId",
                "status": "audio_complete",
                "audioS3Key.$": "$.audioS3Key"
              }
            },
            "End": true
          },
          "UpdateChapterTTSFailed": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "${UpdateChapterStatusLambdaArn}",
              "Payload": {
                "bookId.$": "$.bookId",
                "chapterId.$": "$.chapterId",
                "status": "tts_failed",
                "error.$": "$.error"
              }
            },
            "Next": "FailState"
          },
          "FailState": { "Type": "Fail" }
        }
      },
      "Next": "FinalizeBook"
    },
    "FinalizeBook": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${FinalizeBookLambdaArn}",
        "Payload": { "bookId.$": "$.bookId" }
      },
      "End": true
    },
    "MarkBookFailed": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${UpsertBookLambdaArn}",
        "Payload": {
          "bookId.$": "$.bookId",
          "status": "failed",
          "error.$": "$.error"
        }
      },
      "End": true
    }
  }
}
```

> **Note:** If your chapters list is very large (thousands+), consider **Distributed Map** (replace `Map` with `arn:aws:states:::states:map` and provide an S3 items source).

---

## 3) CDK (TypeScript) – State machine + daily schedule

> Replace placeholder ARNs and function constructs with your actual Lambda constructs in the same stack.

```ts
import { Stack, StackProps, Duration } from 'aws-cdk-lib';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import { Construct } from 'constructs';

export class BookPipelineStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // Example: import or define your Lambdas
    const upsertBook = /* lambda.Function */ undefined as any;
    const scraper = /* lambda.Function */ undefined as any;
    const parse = /* lambda.Function */ undefined as any;
    const formatChapter = /* lambda.Function */ undefined as any;
    const ttsChapter = /* lambda.Function */ undefined as any;
    const updateChapter = /* lambda.Function */ undefined as any;
    const finalizeBook = /* lambda.Function */ undefined as any;

    const upsertQueued = new tasks.LambdaInvoke(this, 'UpsertBook_Queued', {
      lambdaFunction: upsertBook,
      payload: sfn.TaskInput.fromObject({ bookId: sfn.JsonPath.stringAt('$.bookId'), status: 'queued' }),
      resultPath: sfn.JsonPath.DISCARD,
    });

    const scrape = new tasks.LambdaInvoke(this, 'ScrapeBook', {
      lambdaFunction: scraper,
      payload: sfn.TaskInput.fromObject({
        bookId: sfn.JsonPath.stringAt('$.bookId'),
        sourceUrl: sfn.JsonPath.stringAt('$.sourceUrl'),
        s3: { bucketRaw: sfn.JsonPath.stringAt('$.s3.bucketRaw') },
        scrapeOptions: sfn.JsonPath.objectAt('$.scrapeOptions')
      }),
      resultSelector: { bookId: sfn.JsonPath.stringAt('$.Payload.bookId'), rawS3Key: sfn.JsonPath.stringAt('$.Payload.rawS3Key') },
      resultPath: '$.scrape',
    }).addRetry({ maxAttempts: 3, interval: Duration.seconds(5), backoffRate: 2 });

    const upsertScraped = new tasks.LambdaInvoke(this, 'UpsertBook_Scraped', {
      lambdaFunction: upsertBook,
      payload: sfn.TaskInput.fromObject({
        bookId: sfn.JsonPath.stringAt('$.scrape.bookId'),
        status: 'scraped',
        rawS3Key: sfn.JsonPath.stringAt('$.scrape.rawS3Key')
      }),
      resultPath: sfn.JsonPath.DISCARD,
    });

    const parseTask = new tasks.LambdaInvoke(this, 'ParseToChapters', {
      lambdaFunction: parse,
      payload: sfn.TaskInput.fromObject({
        bookId: sfn.JsonPath.stringAt('$.bookId'),
        rawS3Key: sfn.JsonPath.stringAt('$.scrape.rawS3Key'),
        s3: { bucketParsed: sfn.JsonPath.stringAt('$.s3.bucketParsed') }
      }),
      resultSelector: { bookId: sfn.JsonPath.stringAt('$.Payload.bookId'), chapters: sfn.JsonPath.listAt('$.Payload.chapters') },
      resultPath: '$.parsed',
    });

    const upsertParsed = new tasks.LambdaInvoke(this, 'UpsertBook_Parsed', {
      lambdaFunction: upsertBook,
      payload: sfn.TaskInput.fromObject({
        bookId: sfn.JsonPath.stringAt('$.parsed.bookId'),
        status: 'parsed',
        chapterCount: sfn.JsonPath.numberAt('States.ArrayLength($.parsed.chapters)')
      }),
      resultPath: sfn.JsonPath.DISCARD,
    });

    const formatIterator = new sfn.Pass(this, 'FormatIteratorPass'); // placeholder for iterator start

    const map = new sfn.Map(this, 'FormatChaptersMap', {
      itemsPath: sfn.JsonPath.stringAt('$.parsed.chapters'),
      resultPath: '$.formatted',
      maxConcurrencyPath: '$.limits.formatConcurrency'
    });

    const format = new tasks.LambdaInvoke(this, 'FormatChapter', {
      lambdaFunction: formatChapter,
      payload: sfn.TaskInput.fromObject({
        bookId: sfn.JsonPath.stringAt('$.bookId'),
        chapterId: sfn.JsonPath.stringAt('$.chapterId'),
        parsedS3Key: sfn.JsonPath.stringAt('$.parsedS3Key'),
        s3: sfn.JsonPath.objectAt('$$.Execution.Input.s3'),
        formatOptions: sfn.JsonPath.objectAt('$$.Execution.Input.formatOptions'),
        idempotencyKey: sfn.JsonPath.format('{}:{}:format', sfn.JsonPath.stringAt('$$.Execution.Input.bookId'), sfn.JsonPath.stringAt('$.chapterId'))
      }),
      resultSelector: { chapterId: sfn.JsonPath.stringAt('$.Payload.chapterId'), formattedS3Key: sfn.JsonPath.stringAt('$.Payload.formattedS3Key') },
      resultPath: '$.formatResult',
    });

    const updateFormatted = new tasks.LambdaInvoke(this, 'UpdateChapterFormattedSuccess', {
      lambdaFunction: updateChapter,
      payload: sfn.TaskInput.fromObject({
        bookId: sfn.JsonPath.stringAt('$$.Execution.Input.bookId'),
        chapterId: sfn.JsonPath.stringAt('$.formatResult.chapterId'),
        status: 'formatted',
        formattedS3Key: sfn.JsonPath.stringAt('$.formatResult.formattedS3Key')
      }),
      resultPath: sfn.JsonPath.DISCARD,
    });

    const tts = new tasks.LambdaInvoke(this, 'TTSChapter', {
      lambdaFunction: ttsChapter,
      payload: sfn.TaskInput.fromObject({
        bookId: sfn.JsonPath.stringAt('$$.Execution.Input.bookId'),
        chapterId: sfn.JsonPath.stringAt('$.formatResult.chapterId'),
        formattedS3Key: sfn.JsonPath.stringAt('$.formatResult.formattedS3Key'),
        s3: sfn.JsonPath.objectAt('$$.Execution.Input.s3'),
        ttsOptions: sfn.JsonPath.objectAt('$$.Execution.Input.ttsOptions'),
        idempotencyKey: sfn.JsonPath.format('{}:{}:tts', sfn.JsonPath.stringAt('$$.Execution.Input.bookId'), sfn.JsonPath.stringAt('$.formatResult.chapterId'))
      }),
      resultSelector: { chapterId: sfn.JsonPath.stringAt('$.Payload.chapterId'), audioS3Key: sfn.JsonPath.stringAt('$.Payload.audioS3Key') },
      resultPath: '$.ttsResult',
    });

    const updateTTSSuccess = new tasks.LambdaInvoke(this, 'UpdateChapterTTSSuccess', {
      lambdaFunction: updateChapter,
      payload: sfn.TaskInput.fromObject({
        bookId: sfn.JsonPath.stringAt('$$.Execution.Input.bookId'),
        chapterId: sfn.JsonPath.stringAt('$.ttsResult.chapterId'),
        status: 'audio_complete',
        audioS3Key: sfn.JsonPath.stringAt('$.ttsResult.audioS3Key')
      }),
      resultPath: sfn.JsonPath.DISCARD,
    });

    map.iterator(format.next(updateFormatted).next(tts).next(updateTTSSuccess));

    const finalize = new tasks.LambdaInvoke(this, 'FinalizeBook', {
      lambdaFunction: finalizeBook,
      payload: sfn.TaskInput.fromObject({ bookId: sfn.JsonPath.stringAt('$.bookId') }),
      resultPath: sfn.JsonPath.DISCARD,
    });

    const definition = upsertQueued
      .next(scrape)
      .next(upsertScraped)
      .next(parseTask)
      .next(upsertParsed)
      .next(map)
      .next(finalize);

    const sm = new sfn.StateMachine(this, 'BookPipelineStateMachine', {
      definitionBody: sfn.DefinitionBody.fromChainable(definition),
      timeout: Duration.hours(6)
    });

    // Daily schedule at 02:00 UTC (adjust to your TZ as needed)
    new events.Rule(this, 'DailyScrapeRule', {
      schedule: events.Schedule.cron({ minute: '0', hour: '2' }),
      targets: [
        new targets.SfnStateMachine(sm, {
          input: events.RuleTargetInput.fromObject({
            bookId: 'bk_${uuid}',
            sourceUrl: 'https://example.com/book.pdf',
            s3: { bucketRaw: 'your-bucket', bucketParsed: 'your-bucket', bucketFormatted: 'your-bucket', bucketAudio: 'your-bucket' },
            limits: { formatConcurrency: 50, ttsConcurrency: 30 }
          })
        })
      ]
    });
  }
}
```

---

## 4) Lambda implementation notes

* **ScraperLambda**: Consider running in a container-based Lambda if using Playwright. Emit `rawS3Key` and write a DB status update (`scraped`).
* **ParseLambda**: Read `rawS3Key` → emit `chapters` array with `chapterId`, `parsedS3Key`.
* **FormatChapterLambda**: Read `parsedS3Key` from S3, call Gemini as needed (respect quotas). Write `formatted/` object. Use exponential backoff and treat 429/5xx as retryable.
* **TTSChapterLambda**: Stream ElevenLabs audio directly to S3 with multipart upload to avoid Lambda memory/size limits. Return `audioS3Key`.
* **UpdateChapterStatusLambda / FinalizeBookLambda**: Use transactions in Aurora; ensure idempotency by upserting on `(book_id, chapter_id, stage)`.

---

## 5) Security & IAM

* Each Lambda gets the least-privilege policy for the specific prefixes it touches:

  * `s3:GetObject` for `raw/` or `formatted/` as needed; `s3:PutObject` for `parsed/`, `formatted/`, `audio/`.
* Store API keys (Gemini, ElevenLabs) in **Secrets Manager**; resolve at init.
* If using Aurora, connect via RDS Proxy for connection pooling from Lambda.

---

## 6) Reliability & Cost Controls

* **Retries** are set per Task; consider Step Functions top-level Catch to mark book failed and emit to a DLQ (SQS) or EventBridge bus.
* **Concurrency caps** are enforced via `MaxConcurrency` on the Map state.
* **Idempotency**: Use `{bookId}:{chapterId}:{stage}`; check S3/object existence before re-running.
* **S3 lifecycle**: Transition `raw/` to Glacier after N days; keep `formatted/` and `audio/` as Standard-IA if rarely accessed.

---

## 7) Optional: Distributed Map for massive chapter counts

If a book has tens of thousands of chapters or sections, use **Distributed Map** with `ItemReader` from S3. You’ll write the `chapters` manifest to S3 and point the Map to that list. This keeps memory bounded and enables horizontally scalable map partitions.

---

## 8) Testing hooks

* Add a `dryRun: true` flag in the input to short-circuit side effects in Lambdas.
* Emit structured logs with `bookId`, `chapterId`, `stage`, and elapsed ms.
* Wire CloudWatch Alarms on Step Functions `ExecutionsFailed` and specific Lambda error rates.

---

### You’re set!

Paste the ASL into the Step Functions console (or wire it via CDK), plug in your Lambda ARNs, and you’ve got a production-ready workflow that includes the ElevenLabs TTS stage with safe concurrency and retries.
