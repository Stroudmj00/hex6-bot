"""Vercel entry point for the Hex6 web app."""

from __future__ import annotations

from hex6.web import create_app

app = create_app("configs/play.toml")
