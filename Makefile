-include .env

MERIDIAN_WEB ?= ../meridian-web

.PHONY: dev backend frontend backend-share frontend-share

# Start both backend and frontend
dev:
	$(MAKE) backend & $(MAKE) frontend & wait

# Local dev — portless gives stable worktree-aware URLs
backend:
	portless api.meridian uv run meridian chat

frontend:
	cd $(MERIDIAN_WEB) && portless app.meridian pnpm dev

# Share over Tailscale
backend-share:
	portless api.meridian --tailscale uv run meridian chat

frontend-share:
	cd $(MERIDIAN_WEB) && portless app.meridian --tailscale pnpm dev
