const DEFAULT_STATE = {
  cooks: [],
  hasLoadedList: false,
  loadingList: false,
  selectedCookId: null,
  selectedCook: null,
  loadingCook: false,
  search: "",
  draftTags: [],
  draftNotes: "",
  draftDetails: {},
  tagInput: "",
  saving: false,
  justSaved: false,
  confirmingDelete: false,
  deleting: false,
  error: null,
  hiddenSeries: [],
  showDetailOnMobile: false,
  userSelected: false,
  live: null,
  compareCookId: null,
  compareCook: null,
  loadingCompare: false,
};

const COMPACT_MEDIA_QUERY = "(max-width: 870px)";
const CHART_PADDING = { top: 22, right: 16, bottom: 30, left: 46 };
const CHART_MIN_HEIGHT = 220;
const CHART_MAX_HEIGHT = 380;
const X_TICK_STEPS = [5, 10, 15, 30, 60, 90, 120, 180, 240, 360, 480];
const Y_TICK_STEPS = [5, 10, 20, 25, 50, 100];
const STALL_WINDOW_MINUTES = 20;
const STALL_RATE_THRESHOLD = 2;
const STALL_MINIMUM_TEMPERATURE_F = 140;
const STALL_MINIMUM_TEMPERATURE_C = 60;
const COMPARE_DASH = "2 5";
const COMPARE_MATCH_MINUTES = 6;

// Free-text cook details; limits match COOK_ANNOTATION_TEXT_FIELDS in const.py.
const DETAIL_FIELDS = [
  { key: "title", label: "Title", placeholder: "Christmas brisket", maxLength: 120 },
  { key: "food", label: "Food", placeholder: "Brisket, pork butt…", maxLength: 120, suggest: true },
  { key: "weight", label: "Weight", placeholder: "14 lb", maxLength: 40 },
  { key: "pellets", label: "Pellets / wood", placeholder: "Hickory blend", maxLength: 120, suggest: true },
];

const SERIES = [
  { key: "grill_actual", label: "Smoker", color: "var(--pb-grill)" },
  { key: "grill_set", label: "Smoker target", color: "var(--pb-grill)", dash: "6 5", faded: true },
  { key: "probe1_actual", label: "Probe 1", color: "var(--pb-probe1)" },
  { key: "probe2_actual", label: "Probe 2", color: "var(--pb-probe2)" },
];

const ICONS = {
  alert:
    "M11,15H13V17H11V15M11,7H13V13H11V7M12,2C6.47,2 2,6.5 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20Z",
  back: "M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z",
  close:
    "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z",
  download: "M5,20H19V18H5M19,9H15V3H9V9H5L12,16L19,9Z",
  delete:
    "M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19M8,9H16V19H8V9M15.5,4L14.5,3H9.5L8.5,4H5V6H19V4H15.5Z",
  notes: "M21,6V8H3V6H21M3,18H12V16H3V18M3,13H21V11H3V13Z",
  refresh:
    "M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z",
  search:
    "M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z",
};

// Cooks recorded before plain-language errors stored raw flag names
// (for example "NoPellets"); keep in sync with ERROR_DESCRIPTIONS in const.py.
const ERROR_DESCRIPTIONS = {
  Err1: "Error 1: grill temperature sensor fault",
  Err2: "Error 2: controller fault",
  Err3: "Error 3: controller fault",
  HighTempErr: "Grill is too hot (high-temperature error)",
  FanErr: "Combustion fan fault",
  HotErr: "Grill was hot at power-on (hot-start error)",
  MotorErr: "Auger motor fault",
  NoPellets: "Out of pellets",
  ErL: "Fire went out or failed to ignite (low-temperature error)",
};

const describeError = (message) => {
  const codes = String(message ?? "").trim().split(/\s+/);
  return codes[0] && codes.every((code) => code in ERROR_DESCRIPTIONS)
    ? codes.map((code) => ERROR_DESCRIPTIONS[code]).join("; ")
    : message;
};

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

const icon = (name) =>
  `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${ICONS[name]}"></path></svg>`;

// The controller reports a disconnected probe (and an idle target) as 0.
const isTemperature = (value) =>
  typeof value === "number" && Number.isFinite(value) && value > 0;

const minutesBetween = (start, timestamp) => {
  const startMs = new Date(start).getTime();
  const currentMs = new Date(timestamp).getTime();
  if (Number.isNaN(startMs) || Number.isNaN(currentMs)) {
    return 0;
  }
  return Math.max(0, (currentMs - startMs) / 60000);
};

const formatElapsed = (minutes) => {
  if (minutes == null) {
    return "-";
  }
  const totalMinutes = Math.max(0, Math.round(minutes));
  const hours = Math.floor(totalMinutes / 60);
  const remainder = totalMinutes % 60;
  if (hours === 0) {
    return `${remainder}m`;
  }
  return remainder === 0 ? `${hours}h` : `${hours}h ${remainder}m`;
};

const STYLES = `
  :host {
    --pb-grill: var(--pitboss-grill-color, #f57c00);
    --pb-probe1: var(--pitboss-probe1-color, #9c6ade);
    --pb-probe2: var(--pitboss-probe2-color, #26a69a);
    --pb-done: var(--pitboss-done-color, var(--success-color, #43a047));
    --pb-error: var(--error-color, #db4437);
    --pb-card-bg: var(--ha-card-background, var(--card-background-color, #fff));
    --pb-border: var(--divider-color, rgba(0, 0, 0, 0.12));
    --pb-radius: var(--ha-card-border-radius, 12px);
    --pb-muted: var(--secondary-text-color, #727272);
    --pb-accent: var(--primary-color, #03a9f4);
    --pb-toolbar-height: 56px;
    background: var(--primary-background-color, #fafafa);
    color: var(--primary-text-color, #212121);
    display: block;
    font-family: var(--paper-font-body1_-_font-family, inherit);
    min-height: 100vh;
  }
  * {
    box-sizing: border-box;
  }
  button,
  input,
  textarea {
    color: inherit;
    font: inherit;
  }
  button {
    cursor: pointer;
  }
  button:focus-visible {
    outline: 2px solid var(--pb-accent);
    outline-offset: 2px;
  }
  .icon {
    fill: currentColor;
    flex: 0 0 auto;
    height: 20px;
    width: 20px;
  }
  .toolbar {
    align-items: center;
    background: var(--app-header-background-color, var(--pb-accent));
    border-bottom: var(--app-header-border-bottom, none);
    color: var(--app-header-text-color, #fff);
    display: flex;
    gap: 4px;
    height: var(--pb-toolbar-height);
    padding: 0 8px 0 12px;
    position: sticky;
    top: 0;
    z-index: 4;
  }
  .toolbar-title {
    display: flex;
    flex: 1;
    flex-direction: column;
    line-height: 1.2;
    min-width: 0;
    padding-left: 4px;
  }
  .toolbar-title strong {
    font-size: 1.25rem;
    font-weight: 400;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .toolbar-title span {
    font-size: 0.82rem;
    opacity: 0.8;
  }
  .icon-button {
    align-items: center;
    background: transparent;
    border: 0;
    border-radius: 50%;
    display: inline-flex;
    height: 40px;
    justify-content: center;
    padding: 0;
    width: 40px;
  }
  .icon-button:hover {
    background: color-mix(in srgb, currentColor 10%, transparent);
  }
  .icon-button[disabled] {
    cursor: default;
    opacity: 0.5;
  }
  .icon-button.spinning .icon {
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .banner {
    align-items: center;
    background: color-mix(in srgb, var(--pb-error) 12%, var(--pb-card-bg));
    border: 1px solid color-mix(in srgb, var(--pb-error) 35%, transparent);
    border-radius: var(--pb-radius);
    color: var(--primary-text-color);
    display: flex;
    gap: 10px;
    margin: 16px 16px 0;
    padding: 6px 6px 6px 14px;
  }
  .banner > .icon {
    color: var(--pb-error);
  }
  .banner span {
    flex: 1;
  }
  .layout {
    align-items: start;
    display: grid;
    gap: 16px;
    grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
    margin: 0 auto;
    max-width: 1440px;
    padding: 16px;
  }
  .card {
    background: var(--pb-card-bg);
    border: 1px solid var(--ha-card-border-color, var(--pb-border));
    border-radius: var(--pb-radius);
    box-shadow: var(--ha-card-box-shadow, none);
  }
  .card-head {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 8px 16px;
    justify-content: space-between;
    padding: 14px 16px 0;
  }
  h2,
  h3 {
    font-weight: 500;
    margin: 0;
  }
  h3 {
    font-size: 1rem;
  }
  .muted {
    color: var(--pb-muted);
  }

  /* Cook list */
  .list-pane {
    display: flex;
    flex-direction: column;
    max-height: calc(100vh - var(--pb-toolbar-height) - 32px);
    overflow: hidden;
    position: sticky;
    top: calc(var(--pb-toolbar-height) + 16px);
  }
  .list-head {
    border-bottom: 1px solid var(--pb-border);
    padding: 12px;
  }
  .search {
    align-items: center;
    background: var(--secondary-background-color, #f2f2f2);
    border: 1px solid transparent;
    border-radius: 999px;
    color: var(--pb-muted);
    display: flex;
    gap: 8px;
    padding: 0 12px;
  }
  .search:focus-within {
    border-color: var(--pb-accent);
  }
  .search input {
    background: transparent;
    border: 0;
    color: var(--primary-text-color);
    flex: 1;
    min-width: 0;
    outline: none;
    padding: 9px 0;
  }
  .list-body {
    flex: 1;
    overflow-y: auto;
    padding: 4px 8px 12px;
  }
  .month {
    color: var(--pb-muted);
    font-size: 0.78rem;
    font-weight: 500;
    letter-spacing: 0.06em;
    padding: 14px 8px 6px;
    text-transform: uppercase;
  }
  .cook-row {
    align-items: center;
    background: transparent;
    border: 0;
    border-radius: 10px;
    display: flex;
    gap: 12px;
    padding: 8px;
    text-align: left;
    width: 100%;
  }
  .cook-row:hover {
    background: var(--secondary-background-color, rgba(0, 0, 0, 0.04));
  }
  .cook-row.selected {
    background: color-mix(in srgb, var(--pb-accent) 14%, transparent);
  }
  .cook-day {
    align-items: center;
    border: 1px solid var(--pb-border);
    border-radius: 10px;
    display: flex;
    flex: 0 0 44px;
    flex-direction: column;
    height: 48px;
    justify-content: center;
    line-height: 1.1;
  }
  .cook-row.selected .cook-day {
    background: var(--pb-accent);
    border-color: var(--pb-accent);
    color: var(--text-primary-color, #fff);
  }
  .cook-day small {
    font-size: 0.68rem;
    letter-spacing: 0.04em;
    opacity: 0.85;
    text-transform: uppercase;
  }
  .cook-day strong {
    font-size: 1.1rem;
  }
  .cook-row-main {
    flex: 1;
    min-width: 0;
  }
  .cook-row-title {
    align-items: center;
    display: flex;
    font-weight: 500;
    gap: 6px;
  }
  .cook-row-title .icon {
    color: var(--pb-muted);
    height: 16px;
    width: 16px;
  }
  .cook-row-meta {
    color: var(--pb-muted);
    font-size: 0.86rem;
    margin-top: 2px;
  }
  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 6px;
  }
  .tag {
    align-items: center;
    background: color-mix(in srgb, var(--pb-accent) 14%, transparent);
    border-radius: 999px;
    display: inline-flex;
    font-size: 0.76rem;
    gap: 2px;
    line-height: 1;
    padding: 4px 8px;
  }
  .tag.more {
    background: var(--secondary-background-color, rgba(0, 0, 0, 0.06));
    color: var(--pb-muted);
  }
  .list-empty {
    color: var(--pb-muted);
    padding: 24px 12px;
    text-align: center;
  }

  /* Detail */
  .detail {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  .detail-head {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 8px 12px;
  }
  .detail-title {
    flex: 1;
    min-width: 200px;
  }
  .detail-title h2 {
    font-size: 1.5rem;
    line-height: 1.25;
  }
  .detail-title div {
    color: var(--pb-muted);
    margin-top: 2px;
  }
  .detail-actions {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: flex-end;
  }
  .btn {
    align-items: center;
    background: transparent;
    border: 1px solid var(--pb-border);
    border-radius: 999px;
    display: inline-flex;
    gap: 6px;
    min-height: 36px;
    padding: 0 14px;
  }
  .btn:hover:not([disabled]) {
    background: var(--secondary-background-color, rgba(0, 0, 0, 0.04));
  }
  .btn[disabled] {
    cursor: default;
    opacity: 0.5;
  }
  .btn.primary {
    background: var(--pb-accent);
    border-color: var(--pb-accent);
    color: var(--text-primary-color, #fff);
  }
  .btn.primary:hover:not([disabled]) {
    background: color-mix(in srgb, var(--pb-accent) 88%, black);
  }
  .btn.danger {
    color: var(--pb-error);
  }
  .btn.danger.solid {
    background: var(--pb-error);
    border-color: var(--pb-error);
    color: #fff;
  }
  .btn.text {
    border-color: transparent;
  }
  .btn .icon {
    height: 18px;
    width: 18px;
  }
  .confirm-text {
    color: var(--pb-error);
    font-size: 0.92rem;
  }
  .stats {
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  }
  .stat {
    padding: 12px 14px;
  }
  .stat span {
    color: var(--pb-muted);
    display: block;
    font-size: 0.8rem;
  }
  .stat strong {
    display: block;
    font-size: 1.35rem;
    font-weight: 500;
    margin-top: 2px;
  }
  .stat small {
    color: var(--pb-muted);
    display: block;
    font-size: 0.78rem;
    margin-top: 2px;
  }
  .stat.alert {
    border-color: color-mix(in srgb, var(--pb-error) 40%, var(--pb-border));
  }
  .stat.alert strong {
    color: var(--pb-error);
  }
  .stat-dot {
    border-radius: 50%;
    display: inline-block;
    height: 8px;
    margin-right: 6px;
    vertical-align: 1px;
    width: 8px;
  }

  /* Chart */
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .legend-item {
    align-items: center;
    background: transparent;
    border: 1px solid var(--pb-border);
    border-radius: 999px;
    display: inline-flex;
    font-size: 0.82rem;
    gap: 6px;
    padding: 4px 10px;
  }
  .legend-item[aria-pressed="false"] {
    opacity: 0.45;
  }
  .legend-item[aria-pressed="false"] svg {
    filter: grayscale(1);
  }
  .legend-item.static {
    cursor: default;
  }
  .legend-item svg {
    height: 10px;
    width: 22px;
  }
  .chart-frame {
    padding: 8px 8px 4px;
    position: relative;
  }
  .chart-region {
    min-height: ${CHART_MIN_HEIGHT}px;
  }
  .cook-chart {
    display: block;
    overflow: visible;
    touch-action: pan-y;
    user-select: none;
    width: 100%;
  }
  .chart-empty {
    align-items: center;
    color: var(--pb-muted);
    display: flex;
    justify-content: center;
    min-height: ${CHART_MIN_HEIGHT}px;
  }
  .grid-line {
    stroke: var(--pb-border);
    stroke-width: 1;
  }
  .axis-label {
    fill: var(--pb-muted);
    font-size: 12px;
  }
  .stall-band {
    fill: color-mix(in srgb, var(--pb-probe1) 13%, transparent);
  }
  .done-line {
    stroke: var(--pb-done);
    stroke-dasharray: 4 4;
    stroke-width: 1.5;
  }
  .done-label {
    fill: var(--pb-done);
    font-size: 11px;
    font-weight: 600;
  }
  .series-line {
    fill: none;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 2.5;
  }
  .series-line.faded {
    opacity: 0.6;
    stroke-width: 1.75;
  }
  .error-marker {
    cursor: help;
  }
  .error-marker .hitbox {
    fill: transparent;
  }
  .error-marker .dot {
    fill: var(--pb-error);
    stroke: var(--pb-card-bg);
    stroke-width: 2;
  }
  .error-marker .range {
    stroke: var(--pb-error);
    stroke-linecap: round;
    stroke-width: 3;
    opacity: 0.7;
  }
  .hover-line {
    stroke: var(--pb-muted);
    stroke-dasharray: 3 4;
    stroke-width: 1;
  }
  .hover-dot {
    stroke: var(--pb-card-bg);
    stroke-width: 2;
  }
  .chart-tooltip {
    background: var(--pb-card-bg);
    border: 1px solid var(--pb-border);
    border-radius: 10px;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.18);
    font-size: 0.86rem;
    min-width: 168px;
    padding: 8px 10px;
    pointer-events: none;
    position: absolute;
    z-index: 2;
  }
  .chart-tooltip[hidden] {
    display: none;
  }
  .tt-time {
    align-items: baseline;
    border-bottom: 1px solid var(--pb-border);
    display: flex;
    gap: 12px;
    justify-content: space-between;
    margin-bottom: 6px;
    padding-bottom: 6px;
  }
  .tt-time span {
    color: var(--pb-muted);
  }
  .tt-row {
    align-items: center;
    display: flex;
    gap: 8px;
    padding: 1px 0;
  }
  .tt-row span {
    color: var(--pb-muted);
    flex: 1;
  }
  .tt-swatch {
    border-radius: 2px;
    height: 3px;
    width: 12px;
  }
  .tt-stall {
    color: var(--pb-probe1);
    font-size: 0.78rem;
    font-weight: 600;
    margin-top: 4px;
  }

  /* Notes + errors */
  .detail-columns {
    align-items: start;
    display: grid;
    gap: 16px;
    grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
  }
  .detail-columns.single {
    grid-template-columns: minmax(0, 1fr);
  }
  .card-body {
    padding: 12px 16px 16px;
  }
  .field-label {
    color: var(--pb-muted);
    display: block;
    font-size: 0.8rem;
    margin: 4px 0 6px;
  }
  .tag-editor {
    align-items: center;
    background: var(--secondary-background-color, #f2f2f2);
    border: 1px solid transparent;
    border-radius: 10px;
    cursor: text;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    min-height: 42px;
    padding: 6px 8px;
  }
  .tag-editor:focus-within,
  textarea:focus {
    border-color: var(--pb-accent);
  }
  .tag-editor .tag {
    font-size: 0.84rem;
    padding: 3px 4px 3px 10px;
  }
  .tag-remove {
    align-items: center;
    background: transparent;
    border: 0;
    border-radius: 50%;
    display: inline-flex;
    height: 20px;
    justify-content: center;
    padding: 0;
    width: 20px;
  }
  .tag-remove:hover {
    background: color-mix(in srgb, currentColor 14%, transparent);
  }
  .tag-remove .icon {
    height: 14px;
    width: 14px;
  }
  .tag-editor input {
    background: transparent;
    border: 0;
    flex: 1;
    min-width: 120px;
    outline: none;
    padding: 4px 2px;
  }
  textarea {
    background: var(--secondary-background-color, #f2f2f2);
    border: 1px solid transparent;
    border-radius: 10px;
    display: block;
    line-height: 1.45;
    min-height: 140px;
    outline: none;
    padding: 10px 12px;
    resize: vertical;
    width: 100%;
  }
  .editor-footer {
    align-items: center;
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 12px;
  }
  .editor-status {
    color: var(--pb-muted);
    flex: 1;
    font-size: 0.86rem;
  }
  .editor-status.dirty {
    color: var(--warning-color, #f57c00);
  }
  .editor-hint {
    color: var(--pb-muted);
    font-size: 0.76rem;
    margin-top: 6px;
  }
  .error-list {
    display: grid;
    gap: 2px;
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .error-item {
    border-left: 3px solid var(--pb-error);
    padding: 8px 0 8px 12px;
  }
  .error-item + .error-item {
    border-top: 1px solid var(--pb-border);
  }
  .error-item-head {
    color: var(--pb-muted);
    display: flex;
    font-size: 0.8rem;
    gap: 8px;
    justify-content: space-between;
  }
  .error-item-message {
    margin-top: 2px;
    overflow-wrap: anywhere;
  }
  .placeholder {
    align-items: center;
    color: var(--pb-muted);
    display: flex;
    flex-direction: column;
    gap: 6px;
    justify-content: center;
    min-height: 280px;
    padding: 32px;
    text-align: center;
  }
  .placeholder strong {
    color: var(--primary-text-color);
    font-size: 1.1rem;
    font-weight: 500;
  }
  .placeholder p {
    margin: 0;
    max-width: 420px;
  }

  /* Live cook */
  .live-dot {
    animation: pulse 1.8s ease-in-out infinite;
    background: var(--pb-error);
    border-radius: 50%;
    display: inline-block;
    height: 10px;
    width: 10px;
  }
  @keyframes pulse {
    50% {
      opacity: 0.35;
    }
  }
  .cook-row.live .cook-day {
    border-color: color-mix(in srgb, var(--pb-error) 45%, var(--pb-border));
    gap: 4px;
  }
  .cook-row.live.selected .cook-day {
    background: var(--pb-error);
    border-color: var(--pb-error);
  }
  .cook-row.live.selected .live-dot {
    background: #fff;
  }
  .live-badge {
    align-items: center;
    background: color-mix(in srgb, var(--pb-error) 14%, transparent);
    border-radius: 999px;
    color: var(--pb-error);
    display: inline-flex;
    font-size: 0.72rem;
    font-weight: 600;
    gap: 6px;
    letter-spacing: 0.06em;
    margin-left: 10px;
    padding: 3px 9px 3px 7px;
    text-transform: uppercase;
    vertical-align: 4px;
  }
  .live-badge .live-dot {
    height: 7px;
    width: 7px;
  }
  .live-badge.offline {
    background: var(--secondary-background-color, rgba(0, 0, 0, 0.06));
    color: var(--pb-muted);
  }
  .live-badge.offline .live-dot {
    animation: none;
    background: var(--pb-muted);
  }
  .live-alerts:empty {
    display: none;
  }
  .live-alerts {
    display: grid;
    gap: 8px;
  }
  .notice {
    align-items: center;
    border: 1px solid;
    border-radius: var(--pb-radius);
    display: flex;
    gap: 10px;
    padding: 10px 14px;
  }
  .notice.warning {
    background: color-mix(in srgb, var(--pb-error) 10%, var(--pb-card-bg));
    border-color: color-mix(in srgb, var(--pb-error) 35%, transparent);
  }
  .notice.warning .icon {
    color: var(--pb-error);
  }
  .notice.info {
    background: var(--pb-card-bg);
    border-color: var(--pb-border);
    color: var(--pb-muted);
  }
  .stat.done {
    border-color: color-mix(in srgb, var(--pb-done) 50%, var(--pb-border));
  }
  .stat.done small {
    color: var(--pb-done);
    font-weight: 600;
  }
  .stat.stalled small {
    color: var(--pb-probe1);
    font-weight: 600;
  }

  /* Compare + details */
  .chart-tools {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 6px 10px;
    justify-content: flex-end;
  }
  .compare-picker select {
    background: var(--secondary-background-color, #f2f2f2);
    border: 1px solid transparent;
    border-radius: 999px;
    color: var(--primary-text-color);
    font: inherit;
    font-size: 0.86rem;
    max-width: 220px;
    padding: 5px 10px;
  }
  .compare-picker select:focus {
    border-color: var(--pb-accent);
    outline: none;
  }
  .compare-chip {
    padding-right: 4px;
  }
  .compare-chip .tag-remove {
    margin-left: 2px;
  }
  .series-line.compare {
    opacity: 0.55;
    stroke-width: 2;
  }
  .tt-compare {
    border-top: 1px solid var(--pb-border);
    color: var(--pb-muted);
    font-size: 0.78rem;
    margin-top: 6px;
    padding-top: 6px;
  }
  .detail-fields {
    display: grid;
    gap: 4px 12px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    margin-bottom: 8px;
  }
  .detail-fields .field-title {
    grid-column: 1 / -1;
  }
  .text-input {
    background: var(--secondary-background-color, #f2f2f2);
    border: 1px solid transparent;
    border-radius: 10px;
    display: block;
    min-width: 0;
    outline: none;
    padding: 9px 12px;
    width: 100%;
  }
  .text-input:focus {
    border-color: var(--pb-accent);
  }
  .detail-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
  }

  /* Phones and narrow windows: one pane at a time. */
  .root.compact .layout {
    grid-template-columns: minmax(0, 1fr);
    padding: 12px;
  }
  .root.compact .list-pane {
    max-height: none;
    position: static;
  }
  .root.compact .list-body {
    overflow: visible;
  }
  .root.compact.show-detail .list-pane,
  .root.compact:not(.show-detail) .detail-pane {
    display: none;
  }
  .root.compact .detail-columns {
    grid-template-columns: minmax(0, 1fr);
  }
  .root.compact .detail-title h2 {
    font-size: 1.25rem;
  }
  .root.compact .stats {
    gap: 8px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .root.compact .stat {
    padding: 8px 10px;
  }
  .root.compact .stat strong {
    font-size: 1.1rem;
  }
  .root.compact .banner {
    margin: 12px 12px 0;
  }
  .root.compact .detail-fields {
    grid-template-columns: minmax(0, 1fr);
  }
  .root.compact .chart-tools {
    justify-content: flex-start;
  }
`;

class PitbossCookPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._panel = null;
    this._narrow = false;
    this._state = { ...DEFAULT_STATE };
    this._cookLoadRequestId = 0;
    this._prepared = null;
    this._chart = null;
    this._hoverIndex = null;
    this._chartWidth = 0;
    this._liveUnsub = null;
    this._compareRequestId = 0;
    this._mediaQuery = window.matchMedia(COMPACT_MEDIA_QUERY);
    this._onMediaChange = () => this._render();
    this._resizeObserver = new ResizeObserver((entries) => {
      const width = Math.floor(entries[0]?.contentRect.width ?? 0);
      if (width > 0 && width !== this._chartWidth) {
        this._chartWidth = width;
        this._renderChartRegion();
      }
    });

    this.shadowRoot.innerHTML = `<style>${STYLES}</style><div class="root"></div>`;
    this._root = this.shadowRoot.querySelector(".root");
    this._bindEvents();
  }

  // HA updates `hass` on every state change anywhere in the system, so this
  // setter must not re-render or it would clobber typing and chart hover.
  set hass(hass) {
    const firstHass = this._hass == null;
    this._hass = hass;
    const menuButton = this.shadowRoot.querySelector("ha-menu-button");
    if (menuButton) {
      menuButton.hass = hass;
    }
    if (!this._state.hasLoadedList && !this._state.loadingList) {
      this._loadCooks();
    } else if (firstHass) {
      this._render();
    }
    this._subscribeLive();
  }

  get hass() {
    return this._hass;
  }

  set narrow(narrow) {
    if (this._narrow === Boolean(narrow)) {
      return;
    }
    this._narrow = Boolean(narrow);
    this._render();
  }

  get narrow() {
    return this._narrow;
  }

  set panel(panel) {
    this._panel = panel;
    if (!this._state.hasLoadedList && !this._state.loadingList) {
      this._loadCooks();
    }
    this._subscribeLive();
    this._render();
  }

  get panel() {
    return this._panel;
  }

  connectedCallback() {
    this._mediaQuery.addEventListener("change", this._onMediaChange);
    // Pick up cooks that finished while the panel was closed.
    if (this._state.hasLoadedList) {
      this._loadCooks();
    }
    this._subscribeLive();
    this._render();
  }

  disconnectedCallback() {
    this._mediaQuery.removeEventListener("change", this._onMediaChange);
    this._resizeObserver.disconnect();
    this._unsubscribeLive();
  }

  get _configEntryId() {
    return this._panel?.config?.config_entry_id ?? this._panel?.config_entry_id ?? null;
  }

  get _title() {
    return this._panel?.config?.title ?? this._panel?.title ?? "Pit Boss";
  }

  get _isCompact() {
    return this._narrow || this._mediaQuery.matches;
  }

  get _locale() {
    return this._hass?.locale?.language ?? undefined;
  }

  get _liveCook() {
    return this._state.live?.cook ?? null;
  }

  _isLiveSelected() {
    const liveCook = this._liveCook;
    return Boolean(liveCook) && liveCook.id === this._state.selectedCookId;
  }

  // The cook shown in the detail pane: the in-progress cook or an archived one.
  _currentCook() {
    return this._isLiveSelected() ? this._liveCook : this._state.selectedCook;
  }

  // Live updates

  _subscribeLive() {
    if (
      this._liveUnsub
      || !this.isConnected
      || !this._hass?.connection
      || !this._configEntryId
    ) {
      return;
    }
    this._liveUnsub = this._hass.connection
      .subscribeMessage((snapshot) => this._onLiveSnapshot(snapshot), {
        type: "pitboss/subscribe_live",
        config_entry_id: this._configEntryId,
      })
      // Without live updates the panel still works as an archive.
      .catch(() => null);
  }

  _unsubscribeLive() {
    const pending = this._liveUnsub;
    this._liveUnsub = null;
    pending?.then((unsubscribe) => unsubscribe?.()).catch(() => {});
  }

  _onLiveSnapshot(snapshot) {
    const previousCook = this._liveCook;
    const nextCook = snapshot?.cook ?? null;
    const wasLiveSelected = this._isLiveSelected();
    this._state = { ...this._state, live: snapshot };

    if (previousCook && previousCook.id !== nextCook?.id) {
      // The cook finished. A confirmed cook reappears in the archive under the
      // same id, so keep it selected; _loadCooks falls back if it was dropped.
      if (wasLiveSelected) {
        this._state = { ...this._state, selectedCook: null };
      }
      this._loadCooks();
      return;
    }

    if (!previousCook && nextCook) {
      // Jump to the cook in progress unless the user is busy elsewhere.
      if (!this._state.userSelected && !this._isDirty()) {
        this._cookLoadRequestId += 1;
        this._state = {
          ...this._state,
          selectedCookId: nextCook.id,
          loadingCook: false,
          ...this._draftFromCook(nextCook),
        };
      }
      this._render();
      return;
    }

    if (nextCook) {
      this._refreshLive();
    }
  }

  // Updates live readings in place so typing, focus and hover survive.
  _refreshLive() {
    if (!this._root.querySelector(".layout")) {
      return;
    }
    const subtitle = this._root.querySelector(".toolbar-title span");
    if (subtitle) {
      subtitle.textContent = this._toolbarSubtitle();
    }
    const row = this._root.querySelector("[data-live-row]");
    if (row) {
      row.innerHTML = this._renderLiveRowContent();
    }
    if (!this._isLiveSelected()) {
      return;
    }

    const cook = this._liveCook;
    const shownErrors = this._root.querySelectorAll(".error-item").length;
    if (shownErrors !== (cook.errors ?? []).length) {
      this._render();
      return;
    }

    const regions = {
      ".detail-subtitle": () => this._detailSubtitle(cook),
      ".live-alerts": () => this._renderLiveAlerts(cook),
      ".stats-region": () => this._renderStats(cook),
      ".legend-region": () => this._renderLegend(),
    };
    Object.entries(regions).forEach(([selector, render]) => {
      const element = this._root.querySelector(selector);
      if (element) {
        element.innerHTML = render();
      }
    });

    const hoverIndex = this._hoverIndex;
    this._renderChartRegion();
    const samples = this._chart?.data.samples ?? [];
    if (hoverIndex != null && samples.length) {
      this._hoverIndex = Math.min(hoverIndex, samples.length - 1);
      this._showHover(this._hoverIndex);
    }
    this._updateEditorStatus();
  }

  // Data loading

  async _loadCooks() {
    if (!this._hass || !this._configEntryId || this._state.loadingList) {
      return;
    }

    this._patchState({ loadingList: true, error: null });
    try {
      const result = await this._hass.callWS({
        type: "pitboss/list_cooks",
        config_entry_id: this._configEntryId,
      });
      const cooks = result.cooks ?? [];
      const selectionStillExists =
        this._isLiveSelected()
        || cooks.some((cook) => cook.id === this._state.selectedCookId);
      const patch = {
        cooks,
        hasLoadedList: true,
        loadingList: false,
      };
      if (!selectionStillExists) {
        Object.assign(patch, {
          selectedCookId: cooks[0]?.id ?? null,
          selectedCook: null,
          showDetailOnMobile: false,
          ...this._draftFromCook(null),
        });
      }
      this._patchState(patch);
      if (
        this._state.selectedCookId
        && !this._state.selectedCook
        && !this._isLiveSelected()
      ) {
        await this._loadCook(this._state.selectedCookId);
      }
    } catch (err) {
      this._patchState({
        hasLoadedList: true,
        loadingList: false,
        error: err?.message ?? "Failed to load cooks",
      });
    }
  }

  async _loadCook(cookId) {
    if (!this._hass || !this._configEntryId || !cookId) {
      return;
    }

    const requestId = ++this._cookLoadRequestId;
    this._patchState({
      loadingCook: true,
      error: null,
      selectedCookId: cookId,
      confirmingDelete: false,
    });
    try {
      const result = await this._hass.callWS({
        type: "pitboss/get_cook",
        config_entry_id: this._configEntryId,
        cook_id: cookId,
      });
      if (requestId !== this._cookLoadRequestId) {
        return;
      }
      this._patchState({
        selectedCook: result.cook,
        loadingCook: false,
        ...this._draftFromCook(result.cook),
      });
    } catch (err) {
      if (requestId !== this._cookLoadRequestId) {
        return;
      }
      this._patchState({
        loadingCook: false,
        error: err?.message ?? "Failed to load cook",
      });
    }
  }

  async _saveAnnotations() {
    const cook = this._currentCook();
    if (!this._hass || !this._configEntryId || !cook) {
      return;
    }
    this._commitTagInput();
    if (!this._isDirty() || this._state.saving) {
      return;
    }

    const details = Object.fromEntries(
      DETAIL_FIELDS.map(({ key }) => [
        key,
        (this._state.draftDetails[key] ?? "").trim() || null,
      ]),
    );
    this._patchState({ saving: true, error: null });
    try {
      const result = await this._hass.callWS({
        type: "pitboss/update_cook_annotations",
        config_entry_id: this._configEntryId,
        cook_id: cook.id,
        tags: this._state.draftTags,
        notes: this._state.draftNotes.trim() || null,
        ...details,
      });
      const updatedCook = result.cook;
      const patch = { saving: false, justSaved: true };
      if (this._isLiveSelected() && updatedCook.id === cook.id) {
        // The next live snapshot carries these too; patch now so the
        // editor doesn't flash "unsaved" until it arrives.
        const liveCook = { ...cook, annotations: updatedCook.annotations };
        patch.live = { ...this._state.live, cook: liveCook };
        Object.assign(patch, this._draftFromCook(liveCook), { justSaved: true });
      } else {
        const selectedCook = { ...this._state.selectedCook, ...updatedCook };
        Object.assign(patch, {
          cooks: this._state.cooks.map((item) =>
            item.id === updatedCook.id ? updatedCook : item,
          ),
          selectedCook,
          ...this._draftFromCook(selectedCook),
          justSaved: true,
        });
      }
      this._patchState(patch);
    } catch (err) {
      this._patchState({
        saving: false,
        error: err?.message ?? "Failed to save",
      });
    }
  }

  async _setCompare(cookId) {
    const requestId = ++this._compareRequestId;
    if (!cookId) {
      this._patchState({ compareCookId: null, compareCook: null, loadingCompare: false });
      return;
    }
    this._patchState({ compareCookId: cookId, compareCook: null, loadingCompare: true });
    try {
      const result = await this._hass.callWS({
        type: "pitboss/get_cook",
        config_entry_id: this._configEntryId,
        cook_id: cookId,
      });
      if (requestId === this._compareRequestId) {
        this._patchState({ compareCook: result.cook, loadingCompare: false });
      }
    } catch (err) {
      if (requestId === this._compareRequestId) {
        this._patchState({
          compareCookId: null,
          loadingCompare: false,
          error: err?.message ?? "Failed to load the cook to compare",
        });
      }
    }
  }

  _exportCsv() {
    const cook = this._currentCook();
    if (!cook) {
      return;
    }
    const unit = this._unitFor(cook);
    const reading = (value) => (isTemperature(value) ? String(value) : "");
    const rows = [
      [
        "timestamp",
        "elapsed_minutes",
        `smoker_${unit}`,
        `smoker_target_${unit}`,
        `probe1_${unit}`,
        `probe2_${unit}`,
        "probe1_stalled",
      ],
      ...(cook.samples ?? []).map((sample) => [
        sample.timestamp,
        minutesBetween(cook.start, sample.timestamp).toFixed(1),
        reading(sample.grill_actual),
        reading(sample.grill_set),
        reading(sample.probe1_actual),
        reading(sample.probe2_actual),
        typeof sample.probe1_stalled === "boolean" ? String(Number(sample.probe1_stalled)) : "",
      ]),
    ];
    const cell = (value) =>
      /[",\r\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
    const csv = `${rows.map((row) => row.map(cell).join(",")).join("\r\n")}\r\n`;

    const start = new Date(cook.start);
    const date = [
      start.getFullYear(),
      String(start.getMonth() + 1).padStart(2, "0"),
      String(start.getDate()).padStart(2, "0"),
    ].join("-");
    const slug = (cook.annotations?.title ?? "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40);

    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `pitboss-${date}${slug ? `-${slug}` : ""}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async _deleteSelectedCook() {
    const cookId = this._state.selectedCookId;
    if (!this._hass || !this._configEntryId || !cookId) {
      return;
    }

    this._patchState({ deleting: true, error: null });
    try {
      await this._hass.callWS({
        type: "pitboss/delete_cook",
        config_entry_id: this._configEntryId,
        cook_id: cookId,
      });

      const index = this._state.cooks.findIndex((cook) => cook.id === cookId);
      const cooks = this._state.cooks.filter((cook) => cook.id !== cookId);
      const nextCook = cooks[index] ?? cooks[index - 1] ?? null;
      this._patchState({
        cooks,
        deleting: false,
        selectedCookId: nextCook?.id ?? null,
        selectedCook: null,
        showDetailOnMobile: false,
        ...this._draftFromCook(null),
      });
      if (nextCook) {
        await this._loadCook(nextCook.id);
      }
    } catch (err) {
      this._patchState({
        deleting: false,
        confirmingDelete: false,
        error: err?.message ?? "Failed to delete cook",
      });
    }
  }

  // Draft annotations

  _draftFromCook(cook) {
    return {
      draftTags: [...(cook?.annotations?.tags ?? [])],
      draftNotes: cook?.annotations?.notes ?? "",
      draftDetails: Object.fromEntries(
        DETAIL_FIELDS.map(({ key }) => [key, cook?.annotations?.[key] ?? ""]),
      ),
      tagInput: "",
      justSaved: false,
      confirmingDelete: false,
    };
  }

  _isDirty() {
    const cook = this._currentCook();
    if (!cook) {
      return false;
    }
    const savedTags = cook.annotations?.tags ?? [];
    const savedNotes = cook.annotations?.notes ?? "";
    return (
      this._state.tagInput.trim() !== ""
      || DETAIL_FIELDS.some(
        ({ key }) =>
          (this._state.draftDetails[key] ?? "").trim()
          !== (cook.annotations?.[key] ?? "").trim(),
      )
      || this._state.draftNotes.trim() !== savedNotes.trim()
      || this._state.draftTags.length !== savedTags.length
      || this._state.draftTags.some((tag, index) => tag !== savedTags[index])
    );
  }

  _parseTags(raw) {
    const known = new Set(this._state.draftTags.map((tag) => tag.toLocaleLowerCase()));
    const added = [];
    raw.split(",").forEach((part) => {
      const tag = part.trim().toLocaleLowerCase();
      if (tag && !known.has(tag)) {
        known.add(tag);
        added.push(tag);
      }
    });
    return added;
  }

  _commitTagInput() {
    if (!this._state.tagInput.trim()) {
      return;
    }
    this._state = {
      ...this._state,
      draftTags: [...this._state.draftTags, ...this._parseTags(this._state.tagInput)],
      tagInput: "",
    };
  }

  _addTagsFromInput(raw) {
    // Keep anything after the last comma in the input as a partial tag.
    const parts = raw.split(",");
    const pending = parts.pop();
    this._patchState({
      draftTags: [...this._state.draftTags, ...this._parseTags(parts.join(","))],
      tagInput: pending.trimStart(),
      justSaved: false,
    });
  }

  _selectCook(cookId) {
    if (cookId === this._state.selectedCookId) {
      if (this._isCompact && !this._state.showDetailOnMobile) {
        this._patchState({ showDetailOnMobile: true });
      }
      return;
    }
    if (
      this._isDirty()
      && !window.confirm("You have unsaved changes for this cook. Discard them?")
    ) {
      return;
    }
    const compareReset =
      cookId === this._state.compareCookId ? { compareCookId: null, compareCook: null } : {};
    this._state = { ...this._state, showDetailOnMobile: true, userSelected: true, ...compareReset };
    if (cookId === this._liveCook?.id) {
      this._cookLoadRequestId += 1;
      this._patchState({
        selectedCookId: cookId,
        selectedCook: null,
        loadingCook: false,
        ...this._draftFromCook(this._liveCook),
      });
      return;
    }
    this._loadCook(cookId);
  }

  // Events

  _bindEvents() {
    const root = this.shadowRoot;

    root.addEventListener("click", (event) => {
      const actionEl = event.target.closest("[data-action]");
      const action = actionEl?.dataset.action;

      if (!action) {
        if (event.target.closest(".tag-editor")) {
          root.querySelector("[name='tag-input']")?.focus();
        }
        return;
      }

      switch (action) {
        case "refresh":
          this._loadCooks();
          break;
        case "back":
          this._patchState({ showDetailOnMobile: false });
          break;
        case "select-cook":
          this._selectCook(actionEl.dataset.cookId);
          break;
        case "delete":
          this._patchState({ confirmingDelete: true });
          break;
        case "cancel-delete":
          this._patchState({ confirmingDelete: false });
          break;
        case "confirm-delete":
          this._deleteSelectedCook();
          break;
        case "toggle-series":
          this._toggleSeries(actionEl.dataset.series);
          break;
        case "remove-tag":
          this._patchState({
            draftTags: this._state.draftTags.filter(
              (_tag, index) => index !== Number(actionEl.dataset.index),
            ),
            justSaved: false,
          });
          break;
        case "save":
          this._saveAnnotations();
          break;
        case "export-csv":
          this._exportCsv();
          break;
        case "clear-compare":
          this._setCompare(null);
          break;
        case "revert":
          this._patchState(this._draftFromCook(this._currentCook()));
          break;
        case "dismiss-error":
          this._patchState({ error: null });
          break;
        default:
          break;
      }
    });

    root.addEventListener("input", (event) => {
      const { name, value } = event.target;
      if (name === "search") {
        this._state = { ...this._state, search: value };
        this._renderListBody();
      } else if (name === "tag-input") {
        if (value.includes(",")) {
          this._addTagsFromInput(value);
        } else {
          this._state = { ...this._state, tagInput: value, justSaved: false };
          this._updateEditorStatus();
        }
      } else if (name === "notes") {
        this._state = { ...this._state, draftNotes: value, justSaved: false };
        this._updateEditorStatus();
      } else if (event.target.dataset?.field) {
        this._state = {
          ...this._state,
          draftDetails: { ...this._state.draftDetails, [event.target.dataset.field]: value },
          justSaved: false,
        };
        this._updateEditorStatus();
      }
    });

    root.addEventListener("change", (event) => {
      if (event.target.name === "compare") {
        this._setCompare(event.target.value || null);
      }
    });

    root.addEventListener("keydown", (event) => {
      const { name } = event.target;

      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        if (name === "notes" || name === "tag-input" || event.target.dataset?.field) {
          event.preventDefault();
          this._saveAnnotations();
        }
        return;
      }

      if (event.target.dataset?.field && event.key === "Enter") {
        event.preventDefault();
        this._saveAnnotations();
        return;
      }

      if (name === "tag-input") {
        if (event.key === "Enter") {
          event.preventDefault();
          this._addTagsFromInput(`${event.target.value},`);
        } else if (
          event.key === "Backspace"
          && event.target.value === ""
          && this._state.draftTags.length
        ) {
          this._patchState({ draftTags: this._state.draftTags.slice(0, -1) });
        }
        return;
      }

      if (name === "search" && event.key === "Escape" && event.target.value) {
        event.target.value = "";
        this._state = { ...this._state, search: "" };
        this._renderListBody();
        return;
      }

      const row = event.target.closest?.("[data-action='select-cook']");
      if (row && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
        event.preventDefault();
        const rows = [...root.querySelectorAll("[data-action='select-cook']")];
        const next = rows[rows.indexOf(row) + (event.key === "ArrowDown" ? 1 : -1)];
        if (next) {
          next.focus();
          this._selectCook(next.dataset.cookId);
        }
      }
    });

    root.addEventListener("pointermove", (event) => {
      if (event.target.closest?.(".cook-chart")) {
        this._updateHover(event);
      }
    });

    root.addEventListener("pointerdown", (event) => {
      if (event.target.closest?.(".cook-chart")) {
        this._updateHover(event);
      }
    });

    root.addEventListener(
      "pointerleave",
      (event) => {
        if (event.target.classList?.contains("chart-frame")) {
          this._clearHover();
        }
      },
      true,
    );
  }

  _toggleSeries(key) {
    const hidden = new Set(this._state.hiddenSeries);
    if (hidden.has(key)) {
      hidden.delete(key);
    } else {
      hidden.add(key);
    }
    this._state = { ...this._state, hiddenSeries: [...hidden] };
    this.shadowRoot
      .querySelector(`[data-action='toggle-series'][data-series='${key}']`)
      ?.setAttribute("aria-pressed", String(!hidden.has(key)));
    this._renderChartRegion();
  }

  // Rendering

  _patchState(patch) {
    this._state = { ...this._state, ...patch };
    this._render();
  }

  _captureView() {
    const active = this.shadowRoot.activeElement;
    return {
      focusKey: active?.dataset?.focusKey ?? null,
      focusCookId: active?.dataset?.cookId ?? null,
      selectionStart: active?.selectionStart ?? null,
      selectionEnd: active?.selectionEnd ?? null,
      listScroll: this._root.querySelector(".list-body")?.scrollTop ?? 0,
    };
  }

  _restoreView(view) {
    const listBody = this._root.querySelector(".list-body");
    if (listBody) {
      listBody.scrollTop = view.listScroll;
    }

    let target = null;
    if (view.focusKey) {
      target = this._root.querySelector(`[data-focus-key="${view.focusKey}"]`);
    } else if (view.focusCookId) {
      target = this._root.querySelector(
        `[data-cook-id="${CSS.escape(view.focusCookId)}"]`,
      );
    }
    if (!target) {
      return;
    }
    target.focus({ preventScroll: true });
    if (view.selectionStart != null && target.setSelectionRange) {
      try {
        target.setSelectionRange(view.selectionStart, view.selectionEnd);
      } catch (_err) {
        // Not every focusable element supports a selection.
      }
    }
  }

  _render() {
    if (!this._root) {
      return;
    }

    const view = this._captureView();
    const compact = this._isCompact;
    const showDetail = compact && this._state.showDetailOnMobile && this._state.selectedCookId;
    this._root.className = `root${compact ? " compact" : ""}${showDetail ? " show-detail" : ""}`;
    this._root.innerHTML = `
      ${this._renderToolbar()}
      ${this._renderErrorBanner()}
      <div class="layout">
        <section class="list-pane card" aria-label="Cooks">
          ${this._renderListHead()}
          <div class="list-body">${this._renderCookList()}</div>
        </section>
        <section class="detail-pane">${this._renderDetail()}</section>
      </div>
    `;

    const menuButton = this._root.querySelector("ha-menu-button");
    if (menuButton) {
      menuButton.hass = this._hass;
      menuButton.narrow = this._narrow;
    }

    this._resizeObserver.disconnect();
    const chartRegion = this._root.querySelector(".chart-region");
    if (chartRegion) {
      this._chartWidth = Math.floor(chartRegion.clientWidth) || this._chartWidth;
      this._renderChartRegion();
      this._resizeObserver.observe(chartRegion);
    }

    this._updateEditorStatus();
    this._restoreView(view);
  }

  _toolbarSubtitle() {
    const count = this._state.cooks.length;
    const parts = [
      this._state.hasLoadedList ? `${count} ${count === 1 ? "cook" : "cooks"}` : "Cook history",
    ];
    if (this._liveCook) {
      parts.push("cooking now");
    }
    return parts.join(" · ");
  }

  _renderToolbar() {
    const subtitle = this._toolbarSubtitle();
    return `
      <header class="toolbar">
        <ha-menu-button></ha-menu-button>
        <div class="toolbar-title">
          <strong>${escapeHtml(this._title)}</strong>
          <span>${escapeHtml(subtitle)}</span>
        </div>
        <button
          class="icon-button${this._state.loadingList ? " spinning" : ""}"
          data-action="refresh"
          title="Refresh"
          aria-label="Refresh cooks"
          ${this._state.loadingList ? "disabled" : ""}
        >${icon("refresh")}</button>
      </header>
    `;
  }

  _renderErrorBanner() {
    if (!this._state.error) {
      return "";
    }
    return `
      <div class="banner" role="alert">
        ${icon("alert")}
        <span>${escapeHtml(this._state.error)}</span>
        <button class="icon-button" data-action="dismiss-error" aria-label="Dismiss">${icon("close")}</button>
      </div>
    `;
  }

  _renderListHead() {
    return `
      <div class="list-head">
        <label class="search">
          ${icon("search")}
          <input
            name="search"
            data-focus-key="search"
            type="search"
            placeholder="Search tags, notes, dates"
            aria-label="Search cooks"
            value="${escapeHtml(this._state.search)}"
          />
        </label>
      </div>
    `;
  }

  _renderListBody() {
    const listBody = this._root.querySelector(".list-body");
    if (listBody) {
      listBody.innerHTML = this._renderCookList();
    }
  }

  _filteredCooks() {
    const query = this._state.search.trim().toLocaleLowerCase();
    if (!query) {
      return this._state.cooks;
    }
    return this._state.cooks.filter((cook) => {
      const start = new Date(cook.start);
      const haystack = [
        ...(cook.annotations?.tags ?? []),
        cook.annotations?.notes ?? "",
        ...DETAIL_FIELDS.map(({ key }) => cook.annotations?.[key] ?? ""),
        start.toLocaleDateString(this._locale, {
          weekday: "long",
          month: "long",
          day: "numeric",
          year: "numeric",
        }),
        start.toLocaleDateString(this._locale),
      ]
        .join(" ")
        .toLocaleLowerCase();
      return query.split(/\s+/).every((term) => haystack.includes(term));
    });
  }

  _renderLiveRow() {
    const cook = this._liveCook;
    if (!cook) {
      return "";
    }
    const selected = this._isLiveSelected();
    return `
      <div class="month">Now</div>
      <button
        class="cook-row live${selected ? " selected" : ""}"
        data-action="select-cook"
        data-cook-id="${escapeHtml(cook.id)}"
        data-live-row
        ${selected ? 'aria-current="true"' : ""}
      >${this._renderLiveRowContent()}</button>
    `;
  }

  _renderLiveRowContent() {
    const cook = this._liveCook;
    const live = this._state.live;
    if (!cook || !live) {
      return "";
    }
    const probe = live.probe1 ?? {};
    const reading = isTemperature(probe.actual)
      ? `Probe ${this._formatTemp(probe.actual, cook)}${
          isTemperature(probe.target) ? ` → ${this._formatTemp(probe.target, cook)}` : ""
        }`
      : null;
    const status = probe.done
      ? "Done"
      : probe.stalled
        ? "Stalled"
        : probe.eta
          ? `ETA ${this._formatTime(probe.eta)}`
          : null;
    const meta = [
      formatElapsed(minutesBetween(cook.start, new Date())),
      reading,
      status,
    ].filter(Boolean);
    return `
      <div class="cook-day" aria-hidden="true">
        <span class="live-dot"></span>
        <small>Live</small>
      </div>
      <div class="cook-row-main">
        <div class="cook-row-title">${escapeHtml(cook.annotations?.title || "Cooking now")}</div>
        <div class="cook-row-meta">${escapeHtml(meta.join(" · "))}</div>
      </div>
    `;
  }

  _renderCookList() {
    if (!this._state.hasLoadedList) {
      return '<div class="list-empty">Loading cooks…</div>';
    }
    const liveRow = this._renderLiveRow();
    if (this._state.cooks.length === 0) {
      return liveRow || '<div class="list-empty">No cooks recorded yet.</div>';
    }

    const cooks = this._filteredCooks();
    if (cooks.length === 0) {
      return `${liveRow}<div class="list-empty">No cooks match your search.</div>`;
    }

    let currentMonth = null;
    return liveRow + cooks
      .map((cook) => {
        const start = new Date(cook.start);
        const month = start.toLocaleDateString(this._locale, {
          month: "long",
          year: "numeric",
        });
        const monthHeader =
          month === currentMonth ? "" : `<div class="month">${escapeHtml(month)}</div>`;
        currentMonth = month;

        const selected = cook.id === this._state.selectedCookId;
        const tags = cook.annotations?.tags ?? [];
        const visibleTags = tags.slice(0, 3);
        const peakProbe = cook.summary?.peak_probe1_actual;
        const title = cook.annotations?.title;
        const meta = [
          title ? this._formatTime(cook.start) : null,
          cook.annotations?.food,
          this._formatDuration(cook.duration_seconds),
          isTemperature(peakProbe) ? `Probe ${this._formatTemp(peakProbe, cook)}` : null,
          cook.stall_count ? `${cook.stall_count} ${cook.stall_count === 1 ? "stall" : "stalls"}` : null,
        ].filter(Boolean);

        return `
          ${monthHeader}
          <button
            class="cook-row${selected ? " selected" : ""}"
            data-action="select-cook"
            data-cook-id="${escapeHtml(cook.id)}"
            ${selected ? 'aria-current="true"' : ""}
          >
            <div class="cook-day" aria-hidden="true">
              <small>${escapeHtml(start.toLocaleDateString(this._locale, { weekday: "short" }))}</small>
              <strong>${start.getDate()}</strong>
            </div>
            <div class="cook-row-main">
              <div class="cook-row-title">
                ${escapeHtml(title || this._formatTime(cook.start))}
                ${cook.annotations?.notes ? `<span title="Has notes">${icon("notes")}</span>` : ""}
              </div>
              <div class="cook-row-meta">${escapeHtml(meta.join(" · "))}</div>
              ${
                tags.length
                  ? `<div class="tags">${visibleTags
                      .map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`)
                      .join("")}${
                      tags.length > visibleTags.length
                        ? `<span class="tag more">+${tags.length - visibleTags.length}</span>`
                        : ""
                    }</div>`
                  : ""
              }
            </div>
          </button>
        `;
      })
      .join("");
  }

  _renderPlaceholder(title, body = "") {
    return `
      <div class="card placeholder">
        <strong>${escapeHtml(title)}</strong>
        ${body ? `<p>${escapeHtml(body)}</p>` : ""}
      </div>
    `;
  }

  _renderDetail() {
    if (!this._configEntryId) {
      return this._renderPlaceholder(
        "Panel not configured",
        "This panel is missing its Pit Boss config entry. Try reloading the integration.",
      );
    }
    if (!this._state.hasLoadedList) {
      return this._renderPlaceholder("Loading cooks…");
    }
    if (this._state.cooks.length === 0 && !this._liveCook) {
      return this._renderPlaceholder(
        "No cooks yet",
        "Cooks are recorded automatically while the smoker runs. When one finishes, it shows up here with its full temperature graph.",
      );
    }

    const cook = this._currentCook();
    if (!cook && !this._state.selectedCookId) {
      return this._renderPlaceholder("Pick a cook", "Choose a cook from the list to see its graph.");
    }
    if (this._state.loadingCook || !cook) {
      return `${this._renderDetailHeader(
        this._state.cooks.find((item) => item.id === this._state.selectedCookId),
      )}${this._renderPlaceholder("Loading cook…")}`;
    }

    const errors = cook.errors ?? [];
    const isLive = this._isLiveSelected();
    return `
      <div class="detail">
        ${this._renderDetailHeader(cook)}
        ${isLive ? `<div class="live-alerts">${this._renderLiveAlerts(cook)}</div>` : ""}
        <div class="stats-region">${this._renderStats(cook)}</div>
        <div class="card">
          <div class="card-head">
            <h3>Temperatures</h3>
            <div class="chart-tools">
              <div class="legend-region">${this._renderLegend()}</div>
              ${this._renderComparePicker(cook)}
            </div>
          </div>
          <div class="chart-frame">
            <div class="chart-region"></div>
            <div class="chart-tooltip" hidden></div>
          </div>
        </div>
        <div class="detail-columns${errors.length ? "" : " single"}">
          ${this._renderNotesCard()}
          ${errors.length ? this._renderErrorsCard(cook, errors) : ""}
        </div>
      </div>
    `;
  }

  _formatCookDate(cook) {
    const start = new Date(cook.start);
    return start.toLocaleDateString(this._locale, {
      weekday: "long",
      month: "long",
      day: "numeric",
      ...(start.getFullYear() === new Date().getFullYear() ? {} : { year: "numeric" }),
    });
  }

  _detailSubtitle(cook) {
    const live = cook.id === this._liveCook?.id;
    const range = live
      ? `Started ${this._formatTime(cook.start)} · ${formatElapsed(minutesBetween(cook.start, new Date()))} so far`
      : cook.end
        ? `${this._formatTime(cook.start)} – ${this._formatTime(cook.end)}`
        : this._formatTime(cook.start);
    const parts = [cook.annotations?.title ? this._formatCookDate(cook) : null, range];
    return escapeHtml(parts.filter(Boolean).join(" · "));
  }

  _renderDetailHeader(cook) {
    if (!cook) {
      return "";
    }
    const isLive = cook.id === this._liveCook?.id;
    const title = cook.annotations?.title || (isLive ? "Cooking now" : this._formatCookDate(cook));
    const online = this._state.live?.online !== false;
    const badge = isLive
      ? `<span class="live-badge${online ? "" : " offline"}"><span class="live-dot"></span>${
          online ? "Live" : "Offline"
        }</span>`
      : "";
    const facts = [cook.annotations?.food, cook.annotations?.weight, cook.annotations?.pellets]
      .filter(Boolean)
      .map((fact) => `<span class="tag">${escapeHtml(fact)}</span>`)
      .join("");
    const hasSamples = (cook.samples ?? []).length > 0;
    const exportButton = `
      <button class="btn" data-action="export-csv" ${hasSamples ? "" : "disabled"} title="Download the temperature log as CSV">
        ${icon("download")}CSV
      </button>
    `;

    let actions;
    if (isLive) {
      actions = exportButton;
    } else if (this._state.deleting) {
      actions = '<button class="btn danger" disabled>Deleting…</button>';
    } else if (this._state.confirmingDelete) {
      actions = `
        <span class="confirm-text">Delete this cook permanently?</span>
        <button class="btn" data-action="cancel-delete">Cancel</button>
        <button class="btn danger solid" data-action="confirm-delete">Delete</button>
      `;
    } else {
      actions = `
        ${this._state.selectedCook ? exportButton : ""}
        <button class="btn danger" data-action="delete" ${this._state.selectedCook ? "" : "disabled"}>
          ${icon("delete")}Delete
        </button>
      `;
    }

    return `
      <div class="detail-head">
        ${
          this._isCompact
            ? `<button class="icon-button" data-action="back" aria-label="All cooks">${icon("back")}</button>`
            : ""
        }
        <div class="detail-title">
          <h2>${escapeHtml(title)}${badge}</h2>
          <div class="detail-subtitle">${this._detailSubtitle(cook)}</div>
          ${facts ? `<div class="detail-meta">${facts}</div>` : ""}
        </div>
        <div class="detail-actions">${actions}</div>
      </div>
    `;
  }

  _renderLiveAlerts(cook) {
    const live = this._state.live;
    if (!live) {
      return "";
    }
    const notices = [];
    if (live.online === false) {
      notices.push(["warning", "Can't reach the smoker right now. Showing the last readings."]);
    }
    if (live.grill?.alert) {
      const low = isTemperature(live.grill.actual) && live.grill.actual < live.grill.target;
      notices.push([
        "warning",
        `Smoker is at ${this._formatTemp(live.grill.actual, cook)} but set to ${this._formatTemp(live.grill.target, cook)}.${
          low ? " The fire may be out or the hopper empty." : ""
        }`,
      ]);
    }
    if (live.error) {
      notices.push(["warning", live.error]);
    }
    if (!cook.confirmed) {
      notices.push([
        "info",
        "This becomes a saved cook once probe 1 has been in for an hour. Until then, unplugging it discards the graph.",
      ]);
    }
    return notices
      .map(
        ([kind, text]) =>
          `<div class="notice ${kind}" role="${kind === "warning" ? "alert" : "status"}">${icon("alert")}<span>${escapeHtml(text)}</span></div>`,
      )
      .join("");
  }

  _renderLiveStats(cook) {
    const live = this._state.live ?? {};
    const grill = live.grill ?? {};
    const probeTile = (label, probe, color) => {
      if (!probe || (!isTemperature(probe.actual) && !isTemperature(probe.target))) {
        return null;
      }
      let sub;
      let state = "";
      if (probe.done) {
        sub = "Done";
        state = "done";
      } else if (probe.stalled) {
        sub = "Stalled";
        state = "stalled";
      } else if (isTemperature(probe.target)) {
        sub = `→ ${this._formatTemp(probe.target, cook)}${
          probe.eta ? ` · ETA ${this._formatTime(probe.eta)}` : ""
        }`;
      } else {
        sub = "No target";
      }
      return { label, value: this._formatTemp(probe.actual, cook), sub, color, state };
    };
    const errorCount = (cook.errors ?? []).length;
    return [
      {
        label: "Smoker",
        value: this._formatTemp(grill.actual, cook),
        sub: isTemperature(grill.target) ? `set ${this._formatTemp(grill.target, cook)}` : "Off",
        color: "var(--pb-grill)",
        alert: grill.alert,
      },
      probeTile("Probe 1", live.probe1, "var(--pb-probe1)"),
      probeTile("Probe 2", live.probe2, "var(--pb-probe2)"),
      {
        label: "Elapsed",
        value: formatElapsed(minutesBetween(cook.start, new Date())),
        sub: `since ${this._formatTime(cook.start)}`,
      },
      { label: "Stalls", value: String(cook.stall_count ?? 0) },
      errorCount ? { label: "Errors", value: String(errorCount), alert: true } : null,
    ].filter(Boolean);
  }

  _renderStats(cook) {
    if (cook.id === this._liveCook?.id) {
      return this._renderStatTiles(this._renderLiveStats(cook));
    }
    const summary = cook.summary ?? {};
    const errorCount = (cook.errors ?? []).length;
    const tiles = [
      { label: "Duration", value: this._formatDuration(cook.duration_seconds) },
      cook.done_at
        ? {
            label: "Probe done",
            value: formatElapsed(minutesBetween(cook.start, cook.done_at)),
            sub: `at ${this._formatTime(cook.done_at)}`,
          }
        : { label: "Probe done", value: "–", sub: "Target not reached" },
      { label: "Peak smoker", value: this._formatTemp(summary.peak_grill_actual, cook), color: "var(--pb-grill)" },
      { label: "Peak probe 1", value: this._formatTemp(summary.peak_probe1_actual, cook), color: "var(--pb-probe1)" },
      isTemperature(summary.peak_probe2_actual)
        ? { label: "Peak probe 2", value: this._formatTemp(summary.peak_probe2_actual, cook), color: "var(--pb-probe2)" }
        : null,
      { label: "Stalls", value: String(cook.stall_count ?? 0) },
      { label: "Errors", value: String(errorCount), alert: errorCount > 0 },
    ].filter(Boolean);
    return this._renderStatTiles(tiles);
  }

  _renderStatTiles(tiles) {
    return `
      <div class="stats">
        ${tiles
          .map(
            (tile) => `
              <div class="card stat${tile.alert ? " alert" : ""}${tile.state ? ` ${tile.state}` : ""}">
                <span>${
                  tile.color ? `<i class="stat-dot" style="background:${tile.color}"></i>` : ""
                }${escapeHtml(tile.label)}</span>
                <strong>${escapeHtml(tile.value)}</strong>
                ${tile.sub ? `<small>${escapeHtml(tile.sub)}</small>` : ""}
              </div>
            `,
          )
          .join("")}
      </div>
    `;
  }

  _renderLegend() {
    const data = this._getPreparedCook();
    if (!data || data.samples.length === 0) {
      return "";
    }
    const hidden = new Set(this._state.hiddenSeries);
    const items = data.series.map(
      (series) => `
        <button
          class="legend-item"
          data-action="toggle-series"
          data-series="${series.key}"
          aria-pressed="${!hidden.has(series.key)}"
          title="Show or hide ${escapeHtml(series.label)}"
        >
          <svg viewBox="0 0 22 10" aria-hidden="true">
            <line x1="2" y1="5" x2="20" y2="5" stroke="${series.color}" stroke-width="3"
              stroke-linecap="round" ${series.dash ? `stroke-dasharray="4 3"` : ""}></line>
          </svg>
          ${escapeHtml(series.label)}
        </button>
      `,
    );
    if (data.stallSpans.length) {
      items.push(`
        <span class="legend-item static">
          <svg viewBox="0 0 22 10" aria-hidden="true"><rect x="2" y="0" width="18" height="10" rx="2" class="stall-band"></rect></svg>
          Stall
        </span>
      `);
    }
    if (data.compare) {
      items.push(`
        <span class="legend-item static compare-chip" title="Dashed lines show the compared cook, lined up by time since start">
          <svg viewBox="0 0 22 10" aria-hidden="true">
            <line x1="2" y1="5" x2="20" y2="5" stroke="currentColor" stroke-width="2.5" stroke-dasharray="${COMPARE_DASH}"></line>
          </svg>
          ${escapeHtml(data.compare.label)}
          <button class="tag-remove" data-action="clear-compare" aria-label="Stop comparing">${icon("close")}</button>
        </span>
      `);
    }
    return `<div class="legend">${items.join("")}</div>`;
  }

  _cookLabel(cook) {
    const start = new Date(cook.start);
    const date = start.toLocaleDateString(this._locale, {
      month: "short",
      day: "numeric",
      ...(start.getFullYear() === new Date().getFullYear() ? {} : { year: "numeric" }),
    });
    return cook.annotations?.title ? `${cook.annotations.title} (${date})` : date;
  }

  _renderComparePicker(cook) {
    const others = this._state.cooks.filter((item) => item.id !== cook.id);
    if (!others.length) {
      return "";
    }
    const selectedId = this._state.compareCookId;
    return `
      <label class="compare-picker">
        <select name="compare" data-focus-key="compare" aria-label="Compare with another cook">
          <option value="">${this._state.loadingCompare ? "Loading…" : "Compare with…"}</option>
          ${others
            .map(
              (item) =>
                `<option value="${escapeHtml(item.id)}" ${item.id === selectedId ? "selected" : ""}>${escapeHtml(
                  [this._cookLabel(item), item.annotations?.food, this._formatDuration(item.duration_seconds)]
                    .filter(Boolean)
                    .join(" · "),
                )}</option>`,
            )
            .join("")}
        </select>
      </label>
    `;
  }

  _renderNotesCard() {
    const knownTags = new Set();
    this._state.cooks.forEach((cook) =>
      (cook.annotations?.tags ?? []).forEach((tag) => knownTags.add(tag)),
    );
    this._state.draftTags.forEach((tag) => knownTags.delete(tag));

    const suggestions = (key) =>
      [...new Set(this._state.cooks.map((cook) => cook.annotations?.[key]).filter(Boolean))]
        .sort()
        .map((value) => `<option value="${escapeHtml(value)}"></option>`)
        .join("");

    return `
      <div class="card">
        <div class="card-head"><h3>Details</h3></div>
        <div class="card-body">
          <div class="detail-fields">
            ${DETAIL_FIELDS.map(
              (field) => `
                <label class="field-${field.key}">
                  <span class="field-label">${escapeHtml(field.label)}</span>
                  <input
                    class="text-input"
                    name="detail-${field.key}"
                    data-field="${field.key}"
                    data-focus-key="detail-${field.key}"
                    maxlength="${field.maxLength}"
                    autocomplete="off"
                    placeholder="${escapeHtml(field.placeholder)}"
                    ${field.suggest ? `list="pitboss-known-${field.key}"` : ""}
                    value="${escapeHtml(this._state.draftDetails[field.key] ?? "")}"
                  />
                </label>
              `,
            ).join("")}
          </div>
          ${DETAIL_FIELDS.filter((field) => field.suggest)
            .map((field) => `<datalist id="pitboss-known-${field.key}">${suggestions(field.key)}</datalist>`)
            .join("")}
          <span class="field-label">Tags</span>
          <div class="tag-editor">
            ${this._state.draftTags
              .map(
                (tag, index) => `
                  <span class="tag">
                    ${escapeHtml(tag)}
                    <button class="tag-remove" data-action="remove-tag" data-index="${index}" aria-label="Remove tag ${escapeHtml(tag)}">${icon("close")}</button>
                  </span>
                `,
              )
              .join("")}
            <input
              name="tag-input"
              data-focus-key="tag-input"
              list="pitboss-known-tags"
              autocomplete="off"
              placeholder="${this._state.draftTags.length ? "Add tag" : "brisket, overnight, hickory…"}"
              aria-label="Add tag"
              value="${escapeHtml(this._state.tagInput)}"
            />
          </div>
          <datalist id="pitboss-known-tags">
            ${[...knownTags].sort().map((tag) => `<option value="${escapeHtml(tag)}"></option>`).join("")}
          </datalist>
          <label class="field-label" for="pitboss-notes">Notes</label>
          <textarea
            id="pitboss-notes"
            name="notes"
            data-focus-key="notes"
            rows="6"
            placeholder="Rub, wood, wrap time, weather, how it turned out…"
          >${escapeHtml(this._state.draftNotes)}</textarea>
          <div class="editor-footer">
            <span class="editor-status" aria-live="polite"></span>
            <button class="btn text" data-action="revert">Revert</button>
            <button class="btn primary" data-action="save">Save</button>
          </div>
          <div class="editor-hint">Enter or comma adds a tag · Ctrl+Enter saves</div>
        </div>
      </div>
    `;
  }

  // Updates the save bar in place so typing never triggers a full re-render.
  _updateEditorStatus() {
    const status = this._root.querySelector(".editor-status");
    if (!status) {
      return;
    }
    const dirty = this._isDirty();
    const saving = this._state.saving;
    status.classList.toggle("dirty", dirty && !saving);
    status.textContent = saving
      ? "Saving…"
      : dirty
        ? "Unsaved changes"
        : this._state.justSaved
          ? "Saved"
          : "";
    this._root.querySelector("[data-action='save']").disabled = !dirty || saving;
    this._root.querySelector("[data-action='revert']").disabled = !dirty || saving;
  }

  _renderErrorsCard(cook, errors) {
    return `
      <div class="card">
        <div class="card-head"><h3>Errors</h3></div>
        <div class="card-body">
          <ul class="error-list">
            ${errors
              .map((error) => {
                const startMinutes = minutesBetween(cook.start, error.timestamp);
                const end = error.end ?? error.end_timestamp;
                const timing = end
                  ? `${formatElapsed(startMinutes)} – ${formatElapsed(minutesBetween(cook.start, end))}`
                  : formatElapsed(startMinutes);
                return `
                  <li class="error-item">
                    <div class="error-item-head">
                      <span>${escapeHtml(timing)} in · ${escapeHtml(this._formatTime(error.timestamp))}</span>
                      <span>${escapeHtml(error.source ?? "device")}</span>
                    </div>
                    <div class="error-item-message">${escapeHtml(describeError(error.message) ?? "Unknown error")}</div>
                  </li>
                `;
              })
              .join("")}
          </ul>
        </div>
      </div>
    `;
  }

  // Chart

  _getPreparedCook() {
    const cook = this._currentCook();
    if (!cook) {
      return null;
    }
    const compareCook =
      this._state.compareCook && this._state.compareCook.id !== cook.id
        ? this._state.compareCook
        : null;
    if (this._prepared?.cook === cook && this._prepared?.compareCook === compareCook) {
      return this._prepared.data;
    }

    const withMinutes = (item) =>
      (item.samples ?? []).map((sample) => ({
        ...sample,
        minutes: minutesBetween(item.start, sample.timestamp),
      }));
    const samples = withMinutes(cook);
    const lastSampleMinutes = samples.length ? samples[samples.length - 1].minutes : 0;
    let compare = null;
    if (compareCook) {
      const compareSamples = withMinutes(compareCook);
      compare = {
        cook: compareCook,
        label: this._cookLabel(compareCook),
        samples: compareSamples,
        // The setpoint line would just add noise to the comparison.
        series: SERIES.filter(
          (series) =>
            !series.faded
            && compareSamples.some((sample) => isTemperature(sample[series.key])),
        ),
        maxMinutes: compareSamples.length
          ? compareSamples[compareSamples.length - 1].minutes
          : 0,
      };
    }
    const maxMinutes = Math.max(
      1,
      lastSampleMinutes,
      cook.duration_seconds ? cook.duration_seconds / 60 : 0,
      compare?.maxMinutes ?? 0,
    );
    const data = {
      samples,
      maxMinutes,
      compare,
      series: SERIES.filter((series) =>
        samples.some((sample) => isTemperature(sample[series.key])),
      ),
      stallSpans: this._getStallSpans(cook, samples),
      doneMinutes: cook.done_at ? minutesBetween(cook.start, cook.done_at) : null,
      errors: (cook.errors ?? []).map((error) => {
        const minutes = Math.min(maxMinutes, minutesBetween(cook.start, error.timestamp));
        const end = error.end ?? error.end_timestamp;
        return {
          ...error,
          minutes,
          endMinutes: end
            ? Math.min(maxMinutes, Math.max(minutes, minutesBetween(cook.start, end)))
            : minutes,
        };
      }),
    };
    this._prepared = { cook, compareCook, data };
    return data;
  }

  _getStallMinimumTemperature(unit) {
    return unit === "C" ? STALL_MINIMUM_TEMPERATURE_C : STALL_MINIMUM_TEMPERATURE_F;
  }

  _getTemperatureChangeRate(samples) {
    if (samples.length < 2) {
      return null;
    }

    const startMinutes = samples[0].minutes;
    const timePoints = samples.map((sample) => sample.minutes - startMinutes);
    const temperatures = samples.map((sample) => sample.probe1_actual);
    const meanTime = timePoints.reduce((sum, value) => sum + value, 0) / timePoints.length;
    const meanTemp =
      temperatures.reduce((sum, value) => sum + value, 0) / temperatures.length;
    const denominator = timePoints.reduce(
      (sum, value) => sum + (value - meanTime) ** 2,
      0,
    );

    if (denominator <= 0) {
      return null;
    }

    const numerator = timePoints.reduce(
      (sum, value, index) =>
        sum + (value - meanTime) * (temperatures[index] - meanTemp),
      0,
    );

    return (numerator / denominator) * 60;
  }

  _flagsToSpans(samples, flags) {
    const spans = [];
    let spanStart = null;

    flags.forEach((stalled, index) => {
      if (stalled && spanStart == null) {
        spanStart = samples[index].minutes;
      } else if (!stalled && spanStart != null) {
        spans.push({ start: spanStart, end: samples[index].minutes });
        spanStart = null;
      }
    });

    if (spanStart != null) {
      spans.push({ start: spanStart, end: samples[samples.length - 1].minutes });
    }

    return spans.filter((span) => span.end > span.start);
  }

  _getStallSpans(cook, samples) {
    if (samples.length < 2) {
      return [];
    }

    // Newer cooks store the coordinator's stall flag on every sample.
    if (samples.some((sample) => typeof sample.probe1_stalled === "boolean")) {
      return this._flagsToSpans(
        samples,
        samples.map((sample) => sample.probe1_stalled === true),
      );
    }

    // Older cooks: approximate stalls from the probe 1 trend.
    const minimumTemperature = this._getStallMinimumTemperature(cook.unit);
    const flags = samples.map((sample) => {
      if (sample.probe1_actual < minimumTemperature) {
        return false;
      }

      const windowSamples = samples.filter(
        (candidate) =>
          candidate.minutes >= sample.minutes - STALL_WINDOW_MINUTES
          && candidate.minutes <= sample.minutes,
      );
      if (windowSamples.length < 2) {
        return false;
      }

      const windowDuration =
        windowSamples[windowSamples.length - 1].minutes - windowSamples[0].minutes;
      if (windowDuration < STALL_WINDOW_MINUTES) {
        return false;
      }

      const rate = this._getTemperatureChangeRate(windowSamples);
      return rate != null && Math.abs(rate) <= STALL_RATE_THRESHOLD;
    });

    return this._flagsToSpans(samples, flags);
  }

  _renderChartRegion() {
    const region = this._root.querySelector(".chart-region");
    if (!region) {
      this._chart = null;
      return;
    }
    this._hoverIndex = null;
    const tooltip = this._root.querySelector(".chart-tooltip");
    if (tooltip) {
      tooltip.hidden = true;
    }
    region.innerHTML = this._renderChart(this._chartWidth || region.clientWidth || 640);
  }

  _renderChart(width) {
    const data = this._getPreparedCook();
    const cook = this._currentCook();
    if (!data || data.samples.length === 0) {
      this._chart = null;
      return '<div class="chart-empty">No temperature samples were recorded for this cook.</div>';
    }

    const hidden = new Set(this._state.hiddenSeries);
    const series = data.series.filter((item) => !hidden.has(item.key));
    const compareSeries = (data.compare?.series ?? []).filter((item) => !hidden.has(item.key));
    const height = Math.round(
      Math.min(CHART_MAX_HEIGHT, Math.max(CHART_MIN_HEIGHT, width * 0.42)),
    );
    const pad = CHART_PADDING;
    const plotWidth = Math.max(10, width - pad.left - pad.right);
    const plotHeight = height - pad.top - pad.bottom;

    // Y scale fitted to the visible series instead of always starting at 0.
    const values = [
      ...data.samples.flatMap((sample) =>
        series.map((item) => sample[item.key]).filter(isTemperature),
      ),
      ...(data.compare?.samples ?? []).flatMap((sample) =>
        compareSeries.map((item) => sample[item.key]).filter(isTemperature),
      ),
    ];
    const low = values.length ? Math.min(...values) : 0;
    const high = values.length ? Math.max(...values) : 100;
    const maxYTicks = Math.max(3, Math.min(7, Math.floor(plotHeight / 40)));
    const yStep =
      Y_TICK_STEPS.find(
        (step) => Math.ceil(high / step) - Math.floor(low / step) <= maxYTicks,
      ) ?? Math.ceil((high - low) / maxYTicks / 100) * 100;
    const yMin = Math.floor(low / yStep) * yStep;
    let yMax = Math.ceil(high / yStep) * yStep;
    if (yMax <= yMin) {
      yMax = yMin + yStep;
    }

    const maxXTicks = Math.max(2, Math.floor(plotWidth / 70));
    const xStep =
      X_TICK_STEPS.find((step) => data.maxMinutes / step <= maxXTicks)
      ?? X_TICK_STEPS[X_TICK_STEPS.length - 1];

    const x = (minutes) => pad.left + (minutes / data.maxMinutes) * plotWidth;
    const y = (temp) => pad.top + plotHeight - ((temp - yMin) / (yMax - yMin)) * plotHeight;
    const plotTop = pad.top;
    const plotBottom = pad.top + plotHeight;
    const fmt = (value) => value.toFixed(1);

    const yTicks = [];
    for (let tick = yMin; tick <= yMax; tick += yStep) {
      yTicks.push(tick);
    }
    const xTicks = [];
    for (let tick = 0; tick <= data.maxMinutes + 0.001; tick += xStep) {
      xTicks.push(tick);
    }

    // Break lines wherever a probe was unplugged instead of plunging to 0.
    const buildPath = (key, samples = data.samples) => {
      let path = "";
      let penDown = false;
      samples.forEach((sample) => {
        const value = sample[key];
        if (!isTemperature(value)) {
          penDown = false;
          return;
        }
        path += `${penDown ? "L" : "M"}${fmt(x(sample.minutes))},${fmt(y(value))}`;
        penDown = true;
      });
      return path;
    };

    this._chart = { data, series, compareSeries, x, y, width, height, plotTop, plotBottom, cook };

    const unit = this._unitFor(cook);
    const doneX = data.doneMinutes == null ? null : x(Math.min(data.doneMinutes, data.maxMinutes));

    return `
      <svg
        class="cook-chart"
        width="${width}"
        height="${height}"
        viewBox="0 0 ${width} ${height}"
        role="img"
        aria-label="Temperatures over the course of the cook"
      >
        ${data.stallSpans
          .map(
            (span) => `
              <rect class="stall-band" x="${fmt(x(span.start))}" y="${plotTop}"
                width="${fmt(Math.max(2, x(span.end) - x(span.start)))}" height="${plotHeight}">
                <title>Stall: ${escapeHtml(formatElapsed(span.start))} – ${escapeHtml(formatElapsed(span.end))}</title>
              </rect>
            `,
          )
          .join("")}
        ${yTicks
          .map(
            (tick) => `
              <line class="grid-line" x1="${pad.left}" x2="${width - pad.right}" y1="${fmt(y(tick))}" y2="${fmt(y(tick))}"></line>
              <text class="axis-label" x="${pad.left - 8}" y="${fmt(y(tick) + 4)}" text-anchor="end">${tick}°</text>
            `,
          )
          .join("")}
        <text class="axis-label" x="${pad.left - 8}" y="${plotTop - 10}" text-anchor="end">°${escapeHtml(unit)}</text>
        ${xTicks
          .map(
            (tick) => `
              <text class="axis-label" x="${fmt(x(tick))}" y="${height - 8}"
                text-anchor="${tick === 0 ? "start" : "middle"}">${escapeHtml(formatElapsed(tick))}</text>
            `,
          )
          .join("")}
        ${
          doneX == null
            ? ""
            : `
              <line class="done-line" x1="${fmt(doneX)}" x2="${fmt(doneX)}" y1="${plotTop}" y2="${plotBottom}"></line>
              <text class="done-label" x="${fmt(doneX)}" y="${plotTop - 6}"
                text-anchor="${doneX > width - 60 ? "end" : "middle"}">Done</text>
            `
        }
        ${compareSeries
          .map(
            (item) => `
              <path class="series-line compare" d="${buildPath(item.key, data.compare.samples)}"
                stroke="${item.color}" stroke-dasharray="${COMPARE_DASH}"></path>
            `,
          )
          .join("")}
        ${series
          .map(
            (item) => `
              <path class="series-line${item.faded ? " faded" : ""}" d="${buildPath(item.key)}"
                stroke="${item.color}" ${item.dash ? `stroke-dasharray="${item.dash}"` : ""}></path>
            `,
          )
          .join("")}
        ${data.errors
          .map((error) => {
            const startX = x(error.minutes);
            const endX = x(error.endMinutes);
            const markerY = plotBottom - 6;
            return `
              <g class="error-marker">
                <title>${escapeHtml(
                  `${describeError(error.message) ?? "Unknown error"}\n${formatElapsed(error.minutes)} in (${this._formatTime(error.timestamp)}) · ${error.source ?? "device"}`,
                )}</title>
                ${
                  endX > startX
                    ? `<line class="range" x1="${fmt(startX)}" x2="${fmt(endX)}" y1="${markerY}" y2="${markerY}"></line>`
                    : ""
                }
                <circle class="hitbox" cx="${fmt(startX)}" cy="${markerY}" r="10"></circle>
                <circle class="dot" cx="${fmt(startX)}" cy="${markerY}" r="5"></circle>
              </g>
            `;
          })
          .join("")}
        <g class="hover-layer"></g>
      </svg>
    `;
  }

  _updateHover(event) {
    const chart = this._chart;
    if (!chart) {
      return;
    }
    const svg = this._root.querySelector(".cook-chart");
    const rect = svg.getBoundingClientRect();
    if (!rect.width) {
      return;
    }

    const pointerX = ((event.clientX - rect.left) / rect.width) * chart.width;
    let nearestIndex = 0;
    let nearestDistance = Number.POSITIVE_INFINITY;
    chart.data.samples.forEach((sample, index) => {
      const distance = Math.abs(chart.x(sample.minutes) - pointerX);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIndex = index;
      }
    });

    if (nearestIndex !== this._hoverIndex) {
      this._hoverIndex = nearestIndex;
      this._showHover(nearestIndex);
    }
  }

  _showHover(index) {
    const chart = this._chart;
    const layer = this._root.querySelector(".hover-layer");
    const tooltip = this._root.querySelector(".chart-tooltip");
    if (!chart || !layer || !tooltip) {
      return;
    }

    const sample = chart.data.samples[index];
    const sampleX = chart.x(sample.minutes);
    const visible = chart.series.filter((item) => isTemperature(sample[item.key]));

    layer.innerHTML = `
      <line class="hover-line" x1="${sampleX}" x2="${sampleX}" y1="${chart.plotTop}" y2="${chart.plotBottom}"></line>
      ${visible
        .map(
          (item) =>
            `<circle class="hover-dot" cx="${sampleX}" cy="${chart.y(sample[item.key])}" r="4.5" fill="${item.color}"></circle>`,
        )
        .join("")}
    `;

    tooltip.innerHTML = `
      <div class="tt-time">
        <strong>${escapeHtml(formatElapsed(sample.minutes))}</strong>
        <span>${escapeHtml(this._formatTime(sample.timestamp))}</span>
      </div>
      ${
        visible.length
          ? visible
              .map(
                (item) => `
                  <div class="tt-row">
                    <i class="tt-swatch" style="background:${item.color}"></i>
                    <span>${escapeHtml(item.label)}</span>
                    <strong>${escapeHtml(this._formatTemp(sample[item.key], chart.cook))}</strong>
                  </div>
                `,
              )
              .join("")
          : '<div class="tt-row"><span>No readings</span></div>'
      }
      ${sample.probe1_stalled ? '<div class="tt-stall">Probe 1 stalled</div>' : ""}
      ${this._renderCompareTooltip(chart, sample.minutes)}
    `;
    tooltip.hidden = false;

    // The frame has 8px padding around the SVG.
    const frameWidth = tooltip.parentElement.clientWidth;
    const tooltipWidth = tooltip.offsetWidth;
    let left = 8 + sampleX + 14;
    if (left + tooltipWidth > frameWidth - 4) {
      left = 8 + sampleX - 14 - tooltipWidth;
    }
    tooltip.style.left = `${Math.max(4, left)}px`;
    tooltip.style.top = `${8 + chart.plotTop}px`;
  }

  _renderCompareTooltip(chart, minutes) {
    const compare = chart.data.compare;
    if (!compare || !chart.compareSeries.length) {
      return "";
    }
    let nearest = null;
    compare.samples.forEach((sample) => {
      if (!nearest || Math.abs(sample.minutes - minutes) < Math.abs(nearest.minutes - minutes)) {
        nearest = sample;
      }
    });
    if (!nearest || Math.abs(nearest.minutes - minutes) > COMPARE_MATCH_MINUTES) {
      return "";
    }
    const rows = chart.compareSeries
      .filter((item) => isTemperature(nearest[item.key]))
      .map(
        (item) => `
          <div class="tt-row">
            <i class="tt-swatch" style="background:${item.color};opacity:0.55"></i>
            <span>${escapeHtml(item.label)}</span>
            <strong>${escapeHtml(this._formatTemp(nearest[item.key], compare.cook))}</strong>
          </div>
        `,
      )
      .join("");
    return rows ? `<div class="tt-compare">${escapeHtml(compare.label)}</div>${rows}` : "";
  }

  _clearHover() {
    this._hoverIndex = null;
    const layer = this._root.querySelector(".hover-layer");
    if (layer) {
      layer.innerHTML = "";
    }
    const tooltip = this._root.querySelector(".chart-tooltip");
    if (tooltip) {
      tooltip.hidden = true;
    }
  }

  // Formatting

  _unitFor(cook) {
    if (cook?.unit) {
      return cook.unit;
    }
    const configured = this._hass?.config?.unit_system?.temperature ?? "°F";
    return configured.replace("°", "") || "F";
  }

  _formatTemp(value, cook) {
    return isTemperature(value) ? `${Math.round(value)}°${this._unitFor(cook)}` : "–";
  }

  _formatTime(value) {
    if (!value) {
      return "–";
    }
    return new Date(value).toLocaleTimeString(this._locale, {
      hour: "numeric",
      minute: "2-digit",
    });
  }

  _formatDuration(seconds) {
    return seconds == null ? "–" : formatElapsed(seconds / 60);
  }
}

if (!customElements.get("pitboss-cook-panel")) {
  customElements.define("pitboss-cook-panel", PitbossCookPanel);
}
