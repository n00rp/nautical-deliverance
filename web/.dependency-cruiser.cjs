/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: "no-import-outside-web",
      severity: "error",
      comment: "Nothing in web/ may import a path outside web/.",
      from: { pathNot: "^node_modules/" },
      to: { pathNot: "^(src|node_modules)/|^[^/]+$" },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    tsConfig: { fileName: "tsconfig.json" },
  },
};
