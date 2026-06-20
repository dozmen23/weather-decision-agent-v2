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

The first implementation uses `data/venues.json` through `JsonVenueProvider` as
a trusted demo source. `VenueService` depends on the provider interface, so a
future live provider can be swapped in without changing the scoring and safety
rules. In map mode, the selected coordinate is also used as the venue origin, so
demo venue distances are recalculated before sorting. The UI can also show
verified venue candidates as map markers. Google Places can now be selected as
a live provider for map-origin nearby search without letting the LLM invent
venue facts.
Developer Mode exposes a venue filtering trace so rejected venues remain
auditable without showing technical details to regular users.

## Provider Boundary

Current providers:

- `JsonVenueProvider`: reads the controlled demo data set.
- `StaticVenueProvider`: supports tests and controlled in-memory demos.
- `ExternalVenueProvider`: validates structured payloads returned by a future
  Foursquare or similar client.
- `GooglePlacesVenueProvider`: calls Google Places Nearby Search for the
  selected map coordinate and normalizes the response into trusted venue
  candidates.

Runtime selection:

- `VENUE_PROVIDER=json` keeps the controlled demo source active.
- `VENUE_JSON_PATH=/path/to/venues.json` can point to another trusted JSON
  catalog.
- `VENUE_PROVIDER=google_places` enables live Google Places nearby search and
  requires `GOOGLE_PLACES_API_KEY`.
- `VENUE_PROVIDER=external` is reserved for a future live client and must not be
  enabled until that client exists.

The Google Places provider maps activity categories to supported Google place
types, requests a limited field mask, and recalculates distance from the
selected origin. The LLM still cannot create venues, alter distance values, or
bypass venue filters.
Automated fixtures cover every mapped activity category, Google source
attribution, deterministic sorting and filtering, malformed place isolation,
quota error handling, and safe continuation without venues when the live
provider is unavailable.
External provider clients must return a list of structured venue payloads.
Client failures, rate limits, malformed payloads, and duplicate venue names are
wrapped as `VenueCatalogError` so the recommendation flow can fail safely.

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
