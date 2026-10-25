FROM node:22-slim

WORKDIR /app

# Install dependencies first (lockfile is committed)
COPY package.json package-lock.json ./
RUN npm ci

# Copy the rest of the application
COPY . .

EXPOSE 5173

# Dev server for docker-compose (source is bind-mounted). For production, build
# with `npm run build` and serve `dist/` behind the same origin as `/api`.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
