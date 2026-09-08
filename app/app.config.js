// Single-user mobile capability is supplied privately at build/publish time.
// Never commit it or reuse the separately scoped Companion capability.
module.exports = ({ config }) => ({
  ...config,
  extra: {
    ...config.extra,
    researchServerUrl: process.env.PETRARCA_API_URL || '',
  },
});
