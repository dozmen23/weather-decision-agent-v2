# Weather Decision Agent

## Executive Summary

**Team:** Deniz Özmen (2203032), Ömer Şahin (2104101)  
**Status:** Implemented, tested and publicly deployed  
**Date:** June 2026  
**Live demo:** [Open Weather Decision Agent](https://dozmen23-weather-decision-agent.hf.space/)

> **Executive statement:** Weather Decision Agent converts a seven-day weather
> forecast and personal preferences into safe, understandable activity plans.
> It supports real map selection, verified venues and LLM-assisted explanations.

## The Challenge

Most weather applications provide data but leave the interpretation to the
user. Temperature, rain and wind must be considered together, and the same
conditions may be acceptable for one activity but unsafe for another.

The project approaches this as a decision-support problem instead of a simple
weather-display problem.

## The Delivered Solution

Users can select a city or a point on Google Maps, choose a day and describe
their activity preferences. Open-Meteo supplies the forecast. A deterministic
decision layer evaluates:

- weather safety,
- preference match,
- comfort,
- practicality.

Google Places adds verified nearby venues when relevant. The interface separates
a simple **User Mode** from a technical **Developer Mode** that exposes scores,
rule traces, evaluator results and raw weather data.

## Why the Architecture Matters

The initial plan placed the language model at the center of activity selection.
The final architecture deliberately moved safety and scoring into deterministic
code.

The LLM is limited to:

- explaining an approved recommendation,
- generating controlled candidates when necessary,
- acting as a second reviewer.

It cannot change safety thresholds, scores or verified venue information.

## Evidence of Completion

| Area | Result |
| --- | --- |
| Product | Public Streamlit application on Hugging Face Spaces |
| Decision quality | Deterministic safety, fallback and score breakdown |
| Location | City search and Google Maps coordinate selection |
| Venues | Google Places provider with verified Maps links |
| Quality | 159 automated tests and reusable evaluation scenarios |
| Delivery | Docker deployment and GitHub Actions synchronization |

## User-Facing Result

![Final recommendation output](report_assets/final_recommendation.png)

The result starts with a simple weather summary, then shows the selected
activity, why it fits and what the user should pay attention to.

## Current Limits

- Google Places category quality can vary by location.
- Free hosting may introduce a short cold-start delay.
- Personalization currently uses a small feedback-based score adjustment.
- The current forecast selection is limited to the available seven-day window.

## Bottom Line

Weather Decision Agent is a complete small-scale agentic AI product. It is useful
to an end user, inspectable by a developer and designed so that the language
model supports the decision without controlling safety-critical behavior.

