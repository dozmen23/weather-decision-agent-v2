# Project Roadmap

## Completed Foundation

- Seven-day weather forecast retrieval and normalization.
- Agent evaluation for a user-selected forecast date.
- Expanded activity model with practical metadata such as purpose, intensity,
  duration, cost level, weather sensitivity, reservation needs, participant fit,
  and tags.
- Smarter fallback flow that tries exact matches before related indoor
  alternatives and only then broadens to safer unrelated options.
- Weather severity level derived from rain, wind, temperature, and condition:
  `LOW`, `MODERATE`, `HIGH`, `SEVERE`.
- Score breakdowns for each recommendation: `weather_safety`,
  `preference_match`, `comfort_match`, `practicality`, and `total_score`.
- Expanded evaluation scenarios for thunderstorm fallback, high wind fallback,
  high temperature fallback, light rain tolerance, exact preference matches,
  and no safe activity availability.
- Controlled LLM-assisted activity generation when the catalog cannot produce
  a safe recommendation. Generated activities are treated only as candidates
  and must pass deterministic rules, scoring, and evaluation before being shown.
- Lightweight JSONL recommendation history and feedback persistence connected
  to the Streamlit flow.
- User Mode and Developer Mode split in Streamlit. User Mode keeps the
  recommendation flow simple; Developer Mode exposes score breakdowns,
  evaluator checks, LLM review, raw weather data, and agent trace.
- Optional LLM explanation and second-review layer after deterministic
  decisions.

## Next Technical Milestones

1. Keep expanding deterministic and LLM evaluation scenarios as new behavior is
   added.
2. Refine the history view and decide which history details belong in User Mode
   versus Developer Mode.
3. Prepare deployment only after the application workflow is complete.

## Activity Catalog Direction

- Expand carefully by adding high-quality indoor and outdoor alternatives for
  each category instead of many loosely related activities.
- Prioritize walking, running, cycling, sports, culture, social, study,
  photography, and relaxation.
- Keep hard weather limits numeric. Avoid duplicating them with separate
  `rain_safe` or `wind_safe` flags unless a future use case clearly needs
  those fields.

## LLM Boundaries

- The deterministic system makes the main recommendation decision.
- The LLM may explain the result, summarize weather, or act as a second
  reviewer.
- The LLM must not change safety rules, override scores, or directly choose
  unsafe activities.

## User Interface Notes

These items are intentionally postponed until the technical workflow is stable:

- Use consistent, natural Turkish throughout the application.
- Split the interface into User Mode and Developer Mode.
- Keep User Mode focused on simple recommendations and short explanations.
- Move agent trace, evaluator results, score breakdown, raw weather data, and
  LLM review into Developer Mode.
- Show the seven-day forecast as a visual calendar/day selector similar to
  language-learning applications.
- Let users choose a location from a map.
- Improve activity cards, mobile layout, and user-friendly error messages.

## Explicitly Out of Scope For Now

- Login and registration.
- Complex database design.
- Full Google Maps integration.
- Real venue recommendation.
- Advanced ML personalization.
- Mobile app development.
- Letting the LLM directly choose activities.
