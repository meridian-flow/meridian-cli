.PHONY: backend frontend backend-share frontend-share build

# Local dev — portless gives stable worktree-aware URLs
backend:
	portless api.meridian uv run meridian chat

frontend:
	cd frontend && portless app.meridian pnpm dev

# Share over Tailscale
backend-share:
	portless api.meridian --tailscale uv run meridian chat

frontend-share:
	cd frontend && portless app.meridian --tailscale pnpm dev

# Production frontend build
build:
	cd frontend && pnpm build
