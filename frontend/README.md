# Shepherd frontend

Angular 22 app for leaders, built from the Claude Design system in `design-system/`
(tokens, `sh-*` component styles, approved screen mockups in `design-system/screens/`).

```
npm install
npm start            # http://localhost:4300 (port 4200 is used by another local project)
npm run api:types    # regenerate src/app/api/schema.ts from the running backend's OpenAPI
```

The backend must be running (`docker compose up -d` at the repo root). There is no
sign-in yet: the first screen asks which leader you are (demo data, fictional names).
Cards marked `SAMPLE` in the code show fixed sample content for features the backend
doesn't produce yet (absence check-in, reminders, unconnected people, failed sends).
