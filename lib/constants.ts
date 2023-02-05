export const HOSTED_ZONE_NAME = ""; // the name of your already existing hosted zone
export const EMAIL_DOMAIN_NAME = "" // the domain name for your disposable email addresses
export const FRONTEND_DOMAIN_NAME = "" // likely the same as EMAIL_DOMAIN_NAME
export const MAILBOX_TTL = 60 * 60 * 24;
export const CORS_ALLOWED_ORIGINS = [
    `https://${ FRONTEND_DOMAIN_NAME }`,
    "http://localhost:3000"
]