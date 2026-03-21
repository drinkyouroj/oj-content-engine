# Add a New Content Platform

Follow these steps to add a new social/content platform (e.g., TikTok) to the pipeline.

## 1. Add Platform Enum

In `worker/app/models/content_draft.py`, add the new value to the `Platform` enum.

## 2. Create Prompt Template

Create `worker/generation/prompts/<platform>.py` following the pattern of `twitter.py` or `linkedin.py`. The prompt must enforce brand voice and hard filters from the rubric.

## 3. Add Model Config

In `worker/generation/llm_client.py`, add an entry to `GENERATION_MODELS` specifying which Claude model and parameters to use for the new platform.

## 4. Register Platform Builder

In `worker/generation/engine.py`, add the platform builder function to the `_SOCIAL_PLATFORM_BUILDERS` dict so the generation engine knows how to route it.

## 5. Add UI Display Config

In `app/dashboard/review/[topicId]/page.tsx`, add the platform to `PLATFORM_META` with display name, icon, and color.

## 6. Add Platform Button

In `components/topic-actions.tsx`, add the platform to `SOCIAL_PLATFORMS` so it appears as a generation option in the dashboard.

## 7. Write Alembic Migration

Create a migration to add the new enum value to the `platform` column in Postgres:

```bash
cd worker && python -m alembic revision --autogenerate -m "add <platform> to platform enum"
```

Review the generated migration, then apply:

```bash
cd worker && python -m alembic upgrade head
```

## 8. Add Tests

Write tests for the new prompt template in `worker/generation/prompts/test_<platform>.py`. At minimum, test that the prompt produces valid structured output and respects hard filters.

## Checklist

- [ ] `Platform` enum updated
- [ ] Prompt template created
- [ ] Model config added
- [ ] Platform builder registered in engine
- [ ] `PLATFORM_META` updated in review page
- [ ] `SOCIAL_PLATFORMS` updated in topic actions
- [ ] Alembic migration written and applied
- [ ] Tests passing
- [ ] Version bump: MINOR (new platform = new capability)
