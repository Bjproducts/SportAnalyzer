const publicApiUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

const fail = (message) => {
  console.error(`\nNetlify deployment configuration error: ${message}\n`);
  process.exit(1);
};

if (!publicApiUrl) {
  fail(
    "NEXT_PUBLIC_API_BASE_URL is required. Set it in Netlify to your deployed " +
      "FastAPI URL, for example https://api.example.com/api.",
  );
}

let parsedApiUrl;
try {
  parsedApiUrl = new URL(publicApiUrl);
} catch {
  fail("NEXT_PUBLIC_API_BASE_URL must be an absolute URL.");
}

if (parsedApiUrl.protocol !== "https:") {
  fail("NEXT_PUBLIC_API_BASE_URL must use HTTPS for a production deployment.");
}
if (parsedApiUrl.username || parsedApiUrl.password) {
  fail("NEXT_PUBLIC_API_BASE_URL must not contain credentials.");
}
if (["localhost", "127.0.0.1", "::1"].includes(parsedApiUrl.hostname)) {
  fail("NEXT_PUBLIC_API_BASE_URL cannot point to a local machine.");
}
if (!parsedApiUrl.pathname.replace(/\/$/, "").endsWith("/api")) {
  fail("NEXT_PUBLIC_API_BASE_URL must include the API prefix and end in /api.");
}

const exposedSecrets = Object.keys(process.env).filter(
  (name) =>
    name.startsWith("NEXT_PUBLIC_") &&
    /(PASSWORD|SECRET|TOKEN|API[_-]?KEY|PRIVATE[_-]?KEY)/i.test(name),
);
if (exposedSecrets.length) {
  fail(
    `secret-like variables must never be browser-visible: ${exposedSecrets.join(", ")}`,
  );
}

console.log(`Netlify environment verified for ${parsedApiUrl.origin}.`);
