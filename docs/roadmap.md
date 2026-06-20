# Project Roadmap

## Completed Foundation

- Seven-day weather forecast retrieval and normalization.
- Agent evaluation for a user-selected forecast date.
- Coordinate-based weather retrieval for map-selected locations.
- Streamlit location mode for city input or large map-based point selection.
- Card-style seven-day forecast selector in the Streamlit sidebar.
- Expanded activity model with practical metadata such as purpose, intensity,
  duration, cost level, weather sensitivity, reservation needs, participant fit,
  and tags.
- User preference filters for maximum cost, maximum duration, preferred
  intensity, and avoiding reservation-based activities.
- Participant-fit preference for solo, friends, and family contexts.
- Transport ease preference at activity level, ready to be backed by map or
  venue data later.
- Location and venue integration plan for future map and real venue support.
- Trusted demo venue data source and deterministic venue candidate filtering.
- Pluggable venue provider boundary with JSON, static test, and external
  provider adapters.
- Google Places live venue provider wiring for map-origin Nearby Search,
  including API key configuration, type mapping, field masks, and normalized
  venue output.
- Google Maps JavaScript component for point selection and compliant display of
  Google Places markers, using a separate referrer-restricted browser key.
- Google Places evaluation fixtures verify activity-to-place-type coverage,
  trusted source attribution, distance sorting, preference filtering, malformed
  result isolation, and graceful degradation during provider failures.
- Provider-specific quota errors remain diagnosable while an unavailable venue
  lookup never removes an otherwise safe activity recommendation.
- Map-selected venue origin, venue distance recalculation, venue map markers,
  and Developer Mode venue filtering trace.
- Natural filter controls for weather and practicality preferences, such as
  low/medium/high wind or short/medium/long duration instead of raw numbers.
- Smarter fallback flow that tries exact matches before related indoor
  alternatives and only then broadens to safer unrelated options.
- Catalog coverage checks for priority activity categories, ensuring each one
  keeps both outdoor options and close indoor alternatives.
- Weather severity level derived from rain, wind, temperature, and condition:
  `LOW`, `MODERATE`, `HIGH`, `SEVERE`.
- Score breakdowns for each recommendation: `weather_safety`,
  `preference_match`, `comfort_match`, `practicality`, and `total_score`.
- Expanded evaluation scenarios for thunderstorm fallback, high wind fallback,
  high temperature fallback, light rain tolerance, exact preference matches,
  no safe activity availability, coordinate-origin venue sorting, and venue
  filter trace behavior.
- Controlled LLM-assisted activity generation when the catalog cannot produce
  a safe recommendation. Generated activities are treated only as candidates
  and must pass deterministic rules, scoring, and evaluation before being shown.
- LLM safety tests reject invented explanation activities, duplicate or missing
  explanation details, unrelated generated candidates, fake venue fields,
  unsafe generated activities, invalid confidence values, and invalid approvals.
- Lightweight JSONL recommendation history and feedback persistence connected
  to the Streamlit flow.
- Recommendation history keeps verified venue candidate names with each saved
  recommendation, while older history records remain readable.
- Lightweight personalization from feedback history. Repeated negative indoor
  feedback applies only a small indoor practicality penalty.
- User Mode and Developer Mode split in Streamlit. User Mode keeps the
  recommendation flow simple; Developer Mode exposes score breakdowns,
  evaluator checks, LLM review, raw weather data, and agent trace.
- User-facing recommendation cards with plain-language "why this" and
  "watch out" sections.
- Smart fallback explanations that mention the specific weather limits behind
  an indoor alternative, such as rain, wind, temperature, or risk level.
- Turkish User Mode labels for catalog activity names and activity types.
- Split recommendation history so User Mode shows a simple recent activity
  list while Developer Mode keeps raw history/debug details.
- Developer Mode evaluation dashboard for running the scenario suite and
  inspecting pass/fail behavior from the interface.
- Optional LLM explanation and second-review layer after deterministic
  decisions.

## Next Technical Milestones

1. Define the next product scope together after reviewing the completed venue
   provider, Google Places, and evaluation stages.
2. Prepare deployment only after the application workflow is complete.

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
- Keep User Mode focused on simple recommendations and short explanations.
- Move agent trace, evaluator results, score breakdown, raw weather data, and
  LLM review into Developer Mode.
- Show the seven-day forecast as a visual calendar/day selector similar to
  language-learning applications.
- Further polish venue cards and map marker layout.
- Improve activity cards, mobile layout, and user-friendly error messages.

## Explicitly Out of Scope For Now

- Login and registration.
- Complex database design.
- Full Google Maps integration.
- Booking, live opening hours, and route planning.
- Advanced ML personalization.
- Mobile app development.
- Letting the LLM directly choose activities.
