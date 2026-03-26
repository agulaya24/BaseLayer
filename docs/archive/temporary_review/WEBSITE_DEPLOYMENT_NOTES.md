# Website Deployment Notes

## Landing Page Status
- `baselayer-landing.html` updated (v2) — broadened from OpenClaw-only, added before/after section, fixed form
- Form placeholder: needs real Formspree/Buttondown/Mailchimp ID wired in

## Decisions Needed Before Deploying
1. **Domain:** baselayer.ai? getbaselayer.com? Something else?
2. **Hosting:** Vercel, Netlify, or GitHub Pages (all free for static sites)
3. **Email capture:** Formspree (free for 50/month), Buttondown (free for 100 subscribers), or Mailchimp
4. **Use case messaging:** Landing page needs a concrete "use cases" section showing:
   - CLAUDE.md generation (Claude Code users)
   - Journal onboarding (anyone, 15 minutes)
   - MCP server (Claude Desktop/Cursor auto-injection)
   - ChatGPT export analysis (curiosity hook)
5. **Legal:** Privacy policy, terms of service (even minimal ones for a waitlist)

## IP / Security Considerations (Aarik's requirement)
- **What's the open-source boundary?** Must decide before any public release.
- **User data safety:** Local-only processing must be verifiable. No telemetry by default.
- **License choice:** Affects what competitors can do with the code.
- See Task #9 in the session task list for full analysis needed.

## Deployment Steps (when ready)
1. Pick domain + hosting
2. Wire email capture to real service
3. Add use case section to landing page
4. Add minimal privacy policy
5. Push to hosting
6. Test form submission
7. Share URL
