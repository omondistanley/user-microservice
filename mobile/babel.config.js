module.exports = function (api) {
  api.cache(true);
  return {
    // nativewind/babel returns { plugins: [...] } — it must be a preset, not a plugin entry.
    presets: ["babel-preset-expo", "nativewind/babel"],
  };
};
