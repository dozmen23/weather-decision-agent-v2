"""Tests for Streamlit-independent UI helper behavior."""

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agent.planner import AgentAction
from app.models.activity import (
    Activity,
    ActivityIntensity,
    CostLevel,
    TransportEase,
)
from app.models.recommendation import Recommendation
from app.models.recommendation_history import (
    FeedbackValue,
    RecommendationHistoryItem,
)
from app.models.user_preferences import UserPreferences
from app.models.weather_data import WeatherData
from app.models.venue import Venue
from app.services.activity_service import ActivityService
from app.services.history_service import RecommendationHistoryRepository
from app.ui.streamlit_app import (
    _build_attention_items,
    _extract_clicked_coordinates,
    _format_coordinate_label,
    _format_user_recommendation_reason,
    _google_venue_marker_payload,
    _venue_map_key,
    _select_user_explanation,
    build_recommendation_service,
    build_preferences,
    calculate_map_center,
    CoordinateWeatherTool,
    format_activity_name,
    format_activity_type,
    format_condition,
    format_cost_level,
    format_forecast_card_label,
    format_forecast_date,
    format_feedback_value,
    format_evaluation_verdict,
    format_history_recommendations,
    format_history_status,
    format_intensity,
    format_participant_preference,
    format_reservation_requirement,
    format_scenario_result,
    format_severity,
    format_trace_action,
    format_transport_ease,
    format_venue_distance,
    format_venue_distance_level,
    format_venue_filter_status,
    format_venue_provider_label,
    format_venue_transport_ease,
    format_view_mode,
    format_warning,
    get_forecast_date_bounds,
    get_activity_types,
)


class UIHelperTests(unittest.TestCase):
    def test_catalog_activity_types_are_unique_and_sorted(self) -> None:
        activity_types = get_activity_types()

        self.assertEqual(activity_types, sorted(set(activity_types)))
        self.assertIn("walking", activity_types)
        self.assertIn("culture", activity_types)

    def test_form_values_create_domain_preferences(self) -> None:
        preferences = build_preferences(
            preferred_activity_type="walking",
            prefers_outdoor=True,
            temperature_range=(12, 30),
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
        )

        self.assertEqual(
            preferences,
            UserPreferences("walking", True, 12.0, 30.0, 40, 25.0),
        )

    def test_advanced_form_values_create_domain_preferences(self) -> None:
        preferences = build_preferences(
            preferred_activity_type="sports",
            prefers_outdoor=False,
            temperature_range=(10, 28),
            max_precipitation_probability_percent=35,
            max_wind_speed_kmh=20,
            max_cost_level=CostLevel.LOW,
            max_duration_minutes=75,
            preferred_intensity=ActivityIntensity.MODERATE,
            avoid_reservations=True,
            suitable_for="friends",
            max_transport_ease=TransportEase.EASY,
        )

        self.assertEqual(preferences.max_cost_level, CostLevel.LOW)
        self.assertEqual(preferences.max_duration_minutes, 75)
        self.assertIs(
            preferences.preferred_intensity,
            ActivityIntensity.MODERATE,
        )
        self.assertTrue(preferences.avoid_reservations)
        self.assertEqual(preferences.suitable_for, "friends")
        self.assertEqual(preferences.max_transport_ease, TransportEase.EASY)

    def test_invalid_temperature_range_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Minimum sıcaklık"):
            build_preferences(
                preferred_activity_type="walking",
                prefers_outdoor=True,
                temperature_range=(20, 20),
                max_precipitation_probability_percent=40,
                max_wind_speed_kmh=25,
            )

    def test_trace_action_has_readable_label(self) -> None:
        self.assertEqual(
            format_trace_action(AgentAction.LOAD_SAFE_ALTERNATIVES),
            "Güvenli kapalı alan alternatifleri arandı",
        )
        self.assertEqual(
            format_trace_action(AgentAction.LOAD_GENERATED_CANDIDATES),
            "LLM aday aktiviteleri üretildi",
        )

    def test_view_mode_labels_are_stable(self) -> None:
        self.assertEqual(format_view_mode("user"), "User Mode")
        self.assertEqual(format_view_mode("developer"), "Developer Mode")

    def test_user_facing_labels_are_turkish(self) -> None:
        self.assertEqual(
            format_activity_name("Indoor Track Walk"),
            "Kapalı pist yürüyüşü",
        )
        self.assertEqual(format_activity_type("creative"), "Yaratıcı")
        self.assertEqual(format_cost_level(CostLevel.LOW), "Düşük")
        self.assertEqual(format_intensity(ActivityIntensity.HIGH), "Yüksek")
        self.assertEqual(format_intensity(None), "Fark etmez")
        self.assertEqual(format_participant_preference("friends"), "Arkadaşla")
        self.assertEqual(format_transport_ease(TransportEase.EASY), "Kolay olsun")
        self.assertEqual(
            format_venue_transport_ease(TransportEase.EASY),
            "kolay ulaşım",
        )
        self.assertEqual(format_venue_filter_status(True), "Geçti")
        self.assertEqual(format_venue_filter_status(False), "Elendi")
        self.assertEqual(
            format_venue_provider_label("json"),
            "JSON demo katalog",
        )
        self.assertEqual(
            format_venue_provider_label("external"),
            "External provider",
        )
        self.assertEqual(format_condition("Partly cloudy"), "Parçalı bulutlu")
        self.assertEqual(format_severity("MODERATE"), "temkinli")
        self.assertEqual(
            format_warning(
                "Indoor/outdoor setting does not match the user's preference."
            ),
            "Hava nedeniyle açık alan yerine kapalı alan öneriyorum.",
        )

    def test_history_labels_are_user_facing(self) -> None:
        recommendations = [
            RecommendationHistoryItem(
                activity_name="Indoor Track Walk",
                activity_type="walking",
                is_outdoor=False,
                score=90,
            )
        ]

        self.assertEqual(format_feedback_value(None), "Henüz yok")
        self.assertEqual(
            format_feedback_value(FeedbackValue.POSITIVE),
            "Beğendin",
        )
        self.assertEqual(format_history_status("completed"), "Öneri hazırlandı")
        self.assertEqual(
            format_history_status("no_recommendation"),
            "Güvenli öneri bulunamadı",
        )
        self.assertEqual(
            format_history_recommendations(recommendations),
            "Kapalı pist yürüyüşü",
        )

    def test_evaluation_labels_are_readable(self) -> None:
        self.assertEqual(format_evaluation_verdict("approved"), "Onaylandı")
        self.assertEqual(
            format_evaluation_verdict("no_recommendation"),
            "Güvenli öneri yok",
        )
        self.assertEqual(format_scenario_result(True), "Geçti")
        self.assertEqual(format_scenario_result(False), "Kaldı")

    def test_catalog_activity_names_have_user_facing_labels(self) -> None:
        activities = ActivityService().get_all()

        for activity in activities:
            with self.subTest(activity_name=activity.name):
                self.assertNotEqual(
                    format_activity_name(activity.name),
                    activity.name,
                )

    def test_user_explanation_filters_technical_llm_text(self) -> None:
        recommendation = Recommendation(
            activity=Activity(
                "Indoor Track Walk",
                "walking",
                False,
                -20,
                50,
                100,
                100,
            ),
            score=90,
            reasoning="",
            warnings=[
                "Indoor/outdoor setting does not match the user's preference."
            ],
        )

        explanation = _select_user_explanation(
            recommendation,
            "Toplam puan: 90.0/100. Hava güvenliği 30.0/30.",
        )
        attention_items = _build_attention_items(recommendation)

        self.assertNotIn("/100", explanation)
        self.assertIn("kapalı alan", explanation)
        self.assertIn(
            "Hava nedeniyle açık alan yerine kapalı alan öneriyorum.",
            attention_items,
        )

    def test_user_reason_explains_weather_based_fallback(self) -> None:
        recommendation = Recommendation(
            activity=Activity(
                "Indoor Track Running",
                "running",
                False,
                -20,
                50,
                100,
                100,
            ),
            score=90,
            reasoning="",
        )
        preferences = UserPreferences(
            preferred_activity_type="running",
            prefers_outdoor=True,
            min_temperature_celsius=10,
            max_temperature_celsius=28,
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
        )
        weather = WeatherData(
            "Canakkale",
            18,
            55,
            42,
            "Windy",
        )

        reason = _format_user_recommendation_reason(
            recommendation,
            weather,
            preferences,
        )
        attention_items = _build_attention_items(
            recommendation,
            weather,
            preferences,
        )

        self.assertIn("açık alanda koşu", reason)
        self.assertIn("yağış ihtimali %55", reason)
        self.assertIn("rüzgâr 42 km/h", reason)
        self.assertIn("kapalı pist koşusu", reason)
        self.assertIn(
            "Açık alanı yine de tercih edersen hava değişimini tekrar kontrol et.",
            attention_items,
        )

    def test_service_builder_accepts_history_repository_without_llm(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repository = RecommendationHistoryRepository(
                Path(temporary_directory) / "history.jsonl"
            )

            service = build_recommendation_service(
                use_llm=False,
                history_repository=repository,
            )

            self.assertIs(service.history_repository, repository)

    def test_coordinate_weather_tool_uses_coordinate_weather_service(self) -> None:
        class StubCoordinateWeatherService:
            def __init__(self) -> None:
                self.current_calls = []
                self.date_calls = []

            def get_current_weather_for_coordinates(
                self,
                latitude,
                longitude,
                label,
            ):
                self.current_calls.append((latitude, longitude, label))
                return WeatherData(label, 20, 10, 5, "Clear sky")

            def get_weather_for_coordinates_and_date(
                self,
                latitude,
                longitude,
                target_date,
                label,
            ):
                self.date_calls.append((latitude, longitude, target_date, label))
                return WeatherData(
                    label,
                    20,
                    10,
                    5,
                    "Clear sky",
                    forecast_date=target_date,
                )

        service = StubCoordinateWeatherService()
        tool = CoordinateWeatherTool(
            41.0138,
            28.9497,
            "Harita konumu",
            weather_service=service,
        )

        current_weather = tool.get_current_weather("ignored")
        dated_weather = tool.get_weather_for_date(
            "ignored",
            date(2026, 6, 19),
        )

        self.assertEqual(current_weather.city, "Harita konumu")
        self.assertEqual(dated_weather.forecast_date, date(2026, 6, 19))
        self.assertEqual(service.current_calls[0][0], 41.0138)
        self.assertEqual(service.date_calls[0][2], date(2026, 6, 19))

    def test_map_click_payload_extracts_coordinates(self) -> None:
        coordinates = _extract_clicked_coordinates(
            {"last_clicked": {"lat": 40.9903, "lng": 29.029}}
        )

        self.assertEqual(coordinates, (40.9903, 29.029))

        google_coordinates = _extract_clicked_coordinates(
            {"latitude": 41.0123, "longitude": 28.9765}
        )
        self.assertEqual(google_coordinates, (41.0123, 28.9765))

    def test_invalid_map_click_payload_is_ignored(self) -> None:
        self.assertIsNone(_extract_clicked_coordinates(None))
        self.assertIsNone(_extract_clicked_coordinates({}))
        self.assertIsNone(
            _extract_clicked_coordinates(
                {"last_clicked": {"lat": 120, "lng": 29.029}}
            )
        )

    def test_coordinate_label_is_compact(self) -> None:
        self.assertEqual(
            _format_coordinate_label(40.9903123, 29.0290123),
            "40.99031, 29.02901",
        )

    def test_venue_distance_labels_are_user_facing(self) -> None:
        venue = Venue(
            name="Demo AVM Yürüyüş Rotası",
            activity_types=("walking",),
            is_outdoor=False,
            city="Istanbul",
            latitude=41.0632,
            longitude=29.0123,
            distance_km=0.85,
            transport_ease=TransportEase.EASY,
            cost_level=CostLevel.FREE,
            requires_reservation=False,
            source="demo",
        )

        self.assertEqual(format_venue_distance(venue.distance_km), "850 m")
        self.assertEqual(
            format_venue_distance_level(venue.distance_km),
            "çok yakın",
        )
        self.assertEqual(format_venue_distance(3.25), "3.2 km")
        self.assertEqual(format_venue_distance_level(4.9), "yakın")
        self.assertEqual(
            format_venue_distance_level(8),
            "orta uzaklıkta",
        )
        self.assertEqual(format_venue_distance_level(12), "uzak")
        self.assertEqual(
            format_reservation_requirement(venue.requires_reservation),
            "rezervasyonsuz olabilir",
        )
        self.assertEqual(
            format_reservation_requirement(True),
            "rezervasyon gerekebilir",
        )

    def test_venue_map_helpers_are_stable(self) -> None:
        venue = Venue(
            name="Demo AVM Yürüyüş Rotası",
            activity_types=("walking",),
            is_outdoor=False,
            city="Istanbul",
            latitude=41.0632,
            longitude=29.0123,
            distance_km=0.85,
            transport_ease=TransportEase.EASY,
            cost_level=CostLevel.FREE,
            requires_reservation=False,
            source="demo",
        )

        center = calculate_map_center(
            [(41.0, 29.0), (42.0, 30.0)],
        )
        self.assertEqual(center, (41.5, 29.5))
        self.assertEqual(
            calculate_map_center([]),
            (41.0138, 28.9497),
        )
        self.assertNotEqual(
            _venue_map_key([venue], "recommendation_1"),
            _venue_map_key([venue], "recommendation_2"),
        )
        self.assertEqual(
            _google_venue_marker_payload([venue]),
            [
                {
                    "name": "Demo AVM Yürüyüş Rotası",
                    "latitude": 41.0632,
                    "longitude": 29.0123,
                    "google_maps_uri": "",
                }
            ],
        )

    def test_forecast_date_bounds_cover_seven_days(self) -> None:
        first_day, last_day = get_forecast_date_bounds(
            date(2026, 6, 12)
        )

        self.assertEqual(first_day, date(2026, 6, 12))
        self.assertEqual(last_day, date(2026, 6, 18))

    def test_forecast_date_is_formatted_in_turkish(self) -> None:
        self.assertEqual(
            format_forecast_date(date(2026, 6, 13)),
            "13 Haziran 2026, Cumartesi",
        )

    def test_forecast_card_label_summarizes_weather(self) -> None:
        weather = WeatherData(
            city="Istanbul",
            temperature_celsius=22,
            precipitation_probability_percent=35,
            wind_speed_kmh=18,
            condition="Partly cloudy",
            forecast_date=date(2026, 6, 18),
            minimum_temperature_celsius=19,
            maximum_temperature_celsius=25,
        )

        label = format_forecast_card_label(
            weather,
            today=date(2026, 6, 18),
        )

        self.assertIn("Bugün", label)
        self.assertIn("19-25°C", label)
        self.assertIn("%35 yağış", label)
        self.assertIn("temkinli", label)


if __name__ == "__main__":
    unittest.main()
