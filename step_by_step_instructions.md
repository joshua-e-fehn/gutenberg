📋 Book Processing Pipeline – Task Breakdown
Epic 1: Infrastructure Setup
Story 1.1: Provision Aurora PostgreSQL

Task 1.1.1: Create Aurora PostgreSQL cluster (Serverless v2).

Acceptance criteria:

Aurora cluster is provisioned in AWS RDS.

Database book_pipeline exists.

Task 1.1.2: Configure RDS Proxy for Lambda connections.

Acceptance criteria:

Lambdas can connect using IAM Auth via RDS Proxy.

Story 1.2: Setup S3 Storage

Task 1.2.1: Create bucket book-pipeline-artifacts-<account>.

Acceptance criteria:

Bucket exists with folders: raw/, parsed/, formatted/, audio/.

Task 1.2.2: Apply lifecycle rules (archive raw → Glacier after 90 days).

Story 1.3: Secrets Management

Task 1.3.1: Store Aurora DB credentials in Secrets Manager (if not IAM).

Task 1.3.2: Store API keys (Gemini, ElevenLabs) in Secrets Manager.

Acceptance criteria:

Keys can be retrieved via secretsmanager:GetSecretValue by Lambdas.

Epic 2: Database Schema
Story 2.1: Create Tables

Task 2.1.1: Apply schema migrations:

books, book_processing, chapters, chapter_processing, chapter_content, processing_logs.

Task 2.1.2: Create indexes (status, updated_at, etc.).

Acceptance criteria:

Running \dt in psql lists all six tables.

Insert/select test query works.

Epic 3: Step Functions Workflow
Story 3.1: Define State Machine

Task 3.1.1: Write ASL JSON definition for pipeline:

ScrapeBook → ParseBook → FormatChapters (Map, concurrency=10) → GenerateAudio (Map, concurrency=5) → FinalizeBook.

Task 3.1.2: Configure retries & error catchers.

Acceptance criteria:

State machine deploys via CDK/Terraform.

Can be manually started with { "book_id": "<uuid>", "source_url": "..." }.

Epic 4: Lambda Functions
Story 4.1: Scrape Book

Task 4.1.1: Implement ScrapeBookLambda:

Fetch raw book text.

Save to S3 raw/{book_id}/book.txt.

Update book_processing.scrape_status.

Acceptance criteria:

Book text appears in S3 raw/.

scrape_status=complete after run.

Story 4.2: Parse Book

Task 4.2.1: Implement ParseBookLambda:

Read raw text from S3.

Split into chapters.

Insert into chapters + chapter_processing.

Update book_processing.parse_status.

Acceptance criteria:

Chapters rows exist in DB.

parse_status=complete.

Story 4.3: Format Chapters

Task 4.3.1: Implement FormatChapterLambda (per chapter in Map):

Fetch chapter text.

Call Gemini API.

Save formatted text to formatted/.

Update chapter_processing.format_status.

Acceptance criteria:

Formatted chapter appears in S3 formatted/{book_id}/{chapter_id}.txt.

DB updated with format_status=complete.

Story 4.4: Generate Audio

Task 4.4.1: Implement GenerateAudioLambda:

Fetch formatted text.

Call ElevenLabs TTS API.

Save MP3 to audio/{book_id}/{chapter_id}.mp3.

Update chapter_processing.tts_status.

Acceptance criteria:

MP3 file present in S3.

DB updated with tts_status=complete.

Story 4.5: Finalize Book

Task 4.5.1: Implement FinalizeBookLambda:

Verify all chapters tts_status=complete.

Update book_processing.tts_status=complete.

Write entry into processing_logs.

Acceptance criteria:

Book row in DB shows tts_status=complete.

Log entry written.

Epic 5: IAM & Security
Story 5.1: IAM Roles

Task 5.1.1: Create IAM role for Step Functions.

Task 5.1.2: Create IAM roles for Lambdas with least privilege:

S3 GetObject/PutObject

RDS connect

Secrets Manager read

Acceptance criteria:

Lambdas run successfully with correct permissions.

Epic 6: Testing & Validation
Story 6.1: End-to-End Test

Task 6.1.1: Insert test book row into DB.

Task 6.1.2: Start Step Function with book ID.

Task 6.1.3: Verify:

Raw text in raw/.

Chapters parsed in DB.

Formatted text in formatted/.

Audio in audio/.

Book row updated with tts_status=complete.

Logs show all stages.

Acceptance criteria:

Full pipeline executes successfully with no manual intervention.

✅ With this, you can drop each story → task into JIRA (or Linear, Trello, etc.). Each task has inputs, outputs, and testable criteria, so a coding agent (or a team) can pick them up independently.
