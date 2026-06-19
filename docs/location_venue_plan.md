# Location and Venue Plan

This plan prepares the project for map-based location selection and controlled
real venue recommendations without changing the core safety rule: deterministic
logic makes the decision, and the LLM may only explain or review it.

## Step 1: Coordinate-Based Weather

- Let the user choose a city or a map coordinate.
- For city input, keep the current geocoding flow.
- For map input, skip geocoding and call Open-Meteo directly with latitude and
  longitude.
- Keep the same weather normalization, severity, rules, scoring, and
  evaluation path for both inputs.

This step is now supported by `WeatherService` coordinate methods.
Streamlit also includes a map mode backed by `streamlit-folium`; when the user
clicks a point on the map, the same recommendation flow runs without city
geocoding. If the map dependency is unavailable, the UI falls back to manual
latitude/longitude input instead of breaking.

## Step 2: Venue Candidate Source

Venue recommendations should come from a reliable structured source, not from
free-form LLM generation. Possible future sources:

- A maps/places API.
- A curated local JSON data set for demo scenarios.
- A small trusted venue provider adapter.

The first implementation uses `data/venues.json` as a trusted demo source and
`VenueService` as the provider boundary. In map mode, the selected coordinate is
also used as the venue origin, so demo venue distances are recalculated before
sorting. The UI can also show verified venue candidates as map markers. A live
places API can replace that source later without letting the LLM invent venue
facts.
Developer Mode exposes a venue filtering trace so rejected venues remain
auditable without showing technical details to regular users.

Every venue candidate should be normalized into fields such as:

- `venue_name`
- `activity_type`
- `latitude`
- `longitude`
- `distance_km`
- `transport_ease`
- `opening_status`
- `requires_reservation`
- `cost_level`
- `source`

## Step 3: Deterministic Venue Filtering

Venue filtering should happen after activity-type selection:

1. Agent selects a safe activity type or indoor alternative.
2. Venue source returns candidate venues for that activity type.
3. Deterministic filters remove unsuitable venues using distance, transport
   ease, reservation, cost, opening status, and weather suitability.
4. The UI shows the verified venue candidates.

The LLM must not invent venues, override distance, change opening status, or
mark an unsafe venue as safe.

## Step 4: LLM Role

The LLM can:

- Explain why a verified venue fits.
- Summarize weather and travel considerations in natural language.
- Act as a second reviewer.

The LLM cannot:

- Choose an unverified venue.
- Change safety rules or scores.
- Fabricate addresses, opening hours, or availability.

## Out Of Scope Until Venue Data Exists

- Full route planning.
- Live traffic.
- Booking/reservation actions.
- User accounts or saved places.
