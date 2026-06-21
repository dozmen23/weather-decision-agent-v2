# Weather Decision Agent

## Practitioner Notes

This guide is for developers, evaluators and maintainers who need to run,
configure, test or extend the project.

**Live demo:** [Open Weather Decision Agent](https://dozmen23-weather-decision-agent.hf.space/)

## 1. Operating Model

The project follows one important rule:

> **Deterministic code owns safety and scoring. External services provide data.
> The LLM explains an already-approved result.**

## 2. System Flow

| Stage | Responsibility | Main component |
| --- | --- | --- |
| 1 | Collect location, date and preferences | Streamlit UI |
| 2 | Fetch and normalize the seven-day forecast | Open-Meteo service |
| 3 | Calculate risk and reject unsafe options | Rules and scoring |
| 4 | Try an exact match, then a close fallback | Decision agent |
| 5 | Find verified nearby venues | Venue provider / Google Places |
| 6 | Explain the approved recommendation | Optional LLM services |

## 3. Local Setup

Use Python 3.12 and install the project dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and configure only the services that will be
enabled. Never commit `.env` or real API keys.

## 4. Environment Configuration

| Variable | When needed | Purpose |
| --- | --- | --- |
| `VENUE_PROVIDER` | Always | Select `json` or `google_places` |
| `GOOGLE_PLACES_API_KEY` | Google Places mode | Server-side venue search secret |
| `GOOGLE_MAPS_BROWSER_API_KEY` | Google Maps picker | Referrer-restricted browser key |
| `LLM_ENABLED` | Always | Enable or disable LLM assistance |
| `LLM_PROVIDER` | LLM enabled | Select the configured LLM provider |
| `LLM_MODEL` | LLM enabled | Choose the configured model |
| `LLM_API_KEY` | LLM enabled | Private provider credential |

## 5. Running the Application

```bash
streamlit run streamlit_app.py
```

Use **User Mode** for the normal recommendation flow. Use **Developer Mode**
when inspecting rule traces, score components, evaluator results, raw weather
data or provider behavior.

## 6. Decision Behavior

### Risk

Rain, wind, temperature and weather condition are converted into `LOW`,
`MODERATE`, `HIGH` or `SEVERE` risk. User Mode translates these into comfortable,
cautious, risky and very risky labels.

### Matching and Fallback

The agent tries an exact activity match first. If that option is unsafe or
unavailable, it searches for a close alternative. Outdoor walking should fall
back to an indoor walking option before an unrelated activity.

### Scoring

The total score is built from weather safety, preference match, comfort and
practicality. A recommendation must pass deterministic safety checks before its
score or explanation is shown.

## 7. Maps and Venue Providers

The venue layer uses a provider interface:

- JSON data supports deterministic demos and tests.
- Google Places supports live venue results.

Keep the Google Places key on the server. Restrict the browser key to Maps
JavaScript API and approved HTTP referrers such as localhost and the Hugging
Face Space domain.

![Google Maps location picker](report_assets/final_map.png)

## 8. LLM Boundary

The LLM may summarize weather, explain a recommendation, generate controlled
catalog candidates and act as a second reviewer. Every candidate is revalidated.

The LLM must not change:

- risk levels,
- safety rules,
- score components,
- verified venue identity.

## 9. Testing and Evaluation

Run all tests with:

```bash
pytest
```

The current suite contains **159 passing tests**. Evaluation scenarios cover:

- thunderstorms,
- high wind,
- extreme temperature,
- light rain,
- exact preference matches,
- safe stopping when no activity is suitable,
- coordinate-based venue sorting,
- rejection of unsafe or invented LLM output.

## 10. Deployment Workflow

The repository contains a Docker configuration for port `7860`. The public
application runs on Hugging Face Spaces. GitHub Actions synchronizes pushes from
`main` to the Space repository.

Store credentials as Hugging Face **Secrets**:

```text
GOOGLE_PLACES_API_KEY
GOOGLE_MAPS_BROWSER_API_KEY
LLM_API_KEY
```

Store non-sensitive switches as **Variables**:

```text
VENUE_PROVIDER=google_places
LLM_ENABLED=true
LLM_PROVIDER=openai
LLM_MODEL=<configured-model>
```

## 11. Operational Notes

| Situation | Expected handling |
| --- | --- |
| Weather API unavailable | Show a controlled error; do not fabricate weather |
| No safe activity | Stop safely and explain that no option passed |
| Google Places unavailable | Keep the activity result; omit live venues |
| LLM unavailable or invalid | Keep the deterministic result and explanation |
| Free Space is sleeping | Allow a short cold-start delay |

## 12. Known Limits

- Venue categories depend on Google Places coverage.
- Forecast selection is limited to the seven-day window.
- Public demo history is session-based and temporary.
- Personalization is intentionally small and feedback-based.

## 13. Maintenance Priorities

| Priority | Practical action |
| --- | --- |
| Activity quality | Review weak activity-to-venue mappings from real examples |
| Safety | Add an evaluation case before changing a threshold |
| LLM behavior | Revalidate every generated candidate |
| Credentials | Rotate exposed keys and keep API restrictions narrow |
| Deployment | Check GitHub Actions and Space logs after a release |

## 14. Quick Reference

```bash
streamlit run streamlit_app.py   # Run locally
pytest                           # Run tests
git push origin main             # Trigger GitHub/HF sync
```

