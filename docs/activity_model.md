# Activity Model V2

The activity model separates hard weather safety limits from descriptive
metadata used for matching, fallback selection, scoring, and explanations.

## Existing Safety Fields

- `is_outdoor`
- `min_temperature_celsius`
- `max_temperature_celsius`
- `max_precipitation_probability_percent`
- `max_wind_speed_kmh`

These values remain authoritative for deterministic eligibility checks.

## Descriptive and Practicality Fields

- `purpose`: Main reason for doing the activity, such as light exercise.
- `intensity`: `low`, `moderate`, or `high`.
- `duration_minutes`: Typical duration of one session.
- `cost_level`: `free`, `low`, `medium`, or `high`.
- `weather_sensitivity`: `none`, `low`, `moderate`, or `high`.
- `requires_reservation`: Whether advance planning is normally required.
- `suitable_for`: Supported participant profiles.
- `tags`: Search and similarity labels.

## Design Decisions

- `rain_safe` and `wind_safe` are not separate fields because numeric rain and
  wind limits already express those constraints more precisely.
- Metadata does not override hard weather rules.
- Tags and purpose will support smarter fallback matching in a later step.
- User preference fields for cost, duration, and intensity will be introduced
  only when the corresponding scoring behavior is implemented.

## Similarity-Based Fallback

When an exact preferred activity is unsafe or unavailable, the catalog ranks
close indoor alternatives deterministically:

1. Same activity type
2. Same purpose
3. Shared tags
4. Matching intensity

The agent only broadens to unrelated activities if the related search produces
no eligible result. This keeps fallbacks aligned with the user's original goal,
such as outdoor walking to an indoor track or mall walk.
