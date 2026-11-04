"""In-engine contracts between weather data (C1), vessel performance (C2) and routing (C3).

Equality and hashing policy for every contract type:

- Types holding NumPy arrays (`WeatherSample`, `OperatingCondition`, `PerformanceResult`) are
  declared with `eq=False`: equality and hash are identity, so `==` never raises on arrays.
- Value types holding mappings (`VesselSpec`, `RouteLeg`) compare and hash by content through
  `ValueEquality` (mappings are compared as sorted item tuples, recursively), so they can be
  `dict` keys and `functools.lru_cache` arguments.
- All other types are plain frozen dataclasses with the generated field-wise `==` and `hash`.
"""
