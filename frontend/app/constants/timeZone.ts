/**
 * F1 Circuit Timezone Map
 * =======================
 * A curated list of IANA timezone strings for every current F1 venue.
 * Used by the RaceCalendar component to let users view session times in
 * circuit-local time rather than their own browser timezone.
 *
 * To add a new venue, append an entry with the venue label and the
 * correct IANA timezone string.
 * Reference: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
 */
const F1_TIMEZONES = [
  { label: "UK (Silverstone)", value: "Europe/London" },
  { label: "Central Europe (Monza/Spa/Zandvoort)", value: "Europe/Paris" },
  { label: "East Coast (Miami/Montreal)", value: "America/New_York" },
  { label: "Central (Austin/Mexico City)", value: "America/Chicago" },
  { label: "Las Vegas", value: "America/Los_Angeles" },
  { label: "Sao Paulo (Interlagos)", value: "America/Sao_Paulo" },
  { label: "Bahrain (Sakhir)", value: "Asia/Bahrain" },
  { label: "Saudi Arabia (Jeddah)", value: "Asia/Riyadh" },
  { label: "Abu Dhabi (Yas Marina)", value: "Asia/Dubai" },
  { label: "Japan (Suzuka)", value: "Asia/Tokyo" },
  { label: "Singapore (Marina Bay)", value: "Asia/Singapore" },
  { label: "China (Shanghai)", value: "Asia/Shanghai" },
  { label: "Australia (Melbourne)", value: "Australia/Melbourne" },
  { label: "Azerbaijan (Baku)", value: "Asia/Baku" },
];

export default F1_TIMEZONES