const DEFAULT_STATE = {
  cooks: [],
  selectedCookId: null,
  selectedCook: null,
  confirmDeleteCookId: null,
  hasLoadedList: false,
  loadingList: false,
  loadingCook: false,
  saving: false,
  deletingCookId: null,
  error: null,
  draftTags: "",
  draftNotes: "",
  hoverSampleIndex: null,
};

const CHART_WIDTH = 860;
const CHART_HEIGHT = 340;
const CHART_PADDING = { top: 24, right: 18, bottom: 38, left: 50 };
const CHART_TICK_MINUTES = 30;
const STALL_WINDOW_MINUTES = 20;
const STALL_RATE_THRESHOLD = 2;
const STALL_MINIMUM_TEMPERATURE_F = 140;
const STALL_MINIMUM_TEMPERATURE_C = 60;

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

class PitbossCookPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._panel = null;
    this._state = { ...DEFAULT_STATE };
    this._bound = false;
    this._cookLoadRequestId = 0;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._state.loadingList && !this._state.hasLoadedList) {
      this._loadCooks();
    }
    this._render();
  }

  get hass() {
    return this._hass;
  }

  set panel(panel) {
    this._panel = panel;
    this._render();
  }

  get panel() {
    return this._panel;
  }

  connectedCallback() {
    this._render();
  }

  async _loadCooks() {
    if (!this._hass || !this._configEntryId) {
      return;
    }

    this._patchState({ loadingList: true, error: null });
    try {
      const result = await this._hass.callWS({
        type: "pitboss/list_cooks",
        config_entry_id: this._configEntryId,
      });
      const cooks = result.cooks ?? [];
      const selectedCookId = cooks.some(
        (cook) => cook.id === this._state.selectedCookId,
      )
        ? this._state.selectedCookId
        : (cooks[0]?.id ?? null);
      this._patchState({
        cooks,
        hasLoadedList: true,
        selectedCookId,
        loadingList: false,
      });
      if (selectedCookId) {
        await this._loadCook(selectedCookId);
      } else {
        this._patchState({ selectedCook: null, draftTags: "", draftNotes: "" });
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
    this._patchState({ loadingCook: true, error: null, selectedCookId: cookId });
    try {
      const result = await this._hass.callWS({
        type: "pitboss/get_cook",
        config_entry_id: this._configEntryId,
        cook_id: cookId,
      });
      if (
        requestId !== this._cookLoadRequestId
        || this._state.selectedCookId !== cookId
      ) {
        return;
      }

      const cook = result.cook;
      this._patchState({
        selectedCook: cook,
        loadingCook: false,
        draftTags: (cook.annotations?.tags ?? []).join(", "),
        draftNotes: cook.annotations?.notes ?? "",
      });
    } catch (err) {
      if (
        requestId !== this._cookLoadRequestId
        || this._state.selectedCookId !== cookId
      ) {
        return;
      }

      this._patchState({
        loadingCook: false,
        error: err?.message ?? "Failed to load cook",
      });
    }
  }

  async _saveAnnotations() {
    if (!this._hass || !this._configEntryId || !this._state.selectedCookId) {
      return;
    }

    this._patchState({ saving: true, error: null });
    try {
      const tags = this._state.draftTags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean);
      const result = await this._hass.callWS({
        type: "pitboss/update_cook_annotations",
        config_entry_id: this._configEntryId,
        cook_id: this._state.selectedCookId,
        tags,
        notes: this._state.draftNotes.trim() || null,
      });
      const updatedCook = result.cook;
      const cooks = this._state.cooks.map((cook) =>
        cook.id === updatedCook.id ? updatedCook : cook,
      );
      this._patchState({
        cooks,
        selectedCook: {
          ...this._state.selectedCook,
          ...updatedCook,
        },
        saving: false,
      });
    } catch (err) {
      this._patchState({
        saving: false,
        error: err?.message ?? "Failed to save annotations",
      });
    }
  }

  async _deleteCook(cookId) {
    if (!this._hass || !this._configEntryId || !cookId) {
      return;
    }

    const cook = this._state.cooks.find((item) => item.id === cookId);
    const label = cook ? this._formatTimestamp(cook.start) : cookId;
    if (!window.confirm(`Delete cook ${label}? This cannot be undone.`)) {
      return;
    }

    this._patchState({ deletingCookId: cookId, error: null });
    try {
      await this._hass.callWS({
        type: "pitboss/delete_cook",
        config_entry_id: this._configEntryId,
        cook_id: cookId,
      });

      const cooks = this._state.cooks.filter((item) => item.id !== cookId);
      const deletedSelectedCook = this._state.selectedCookId === cookId;
      const nextSelectedCookId = deletedSelectedCook
        ? (cooks[0]?.id ?? null)
        : this._state.selectedCookId;

      this._patchState({
        cooks,
        deletingCookId: null,
        selectedCookId: nextSelectedCookId,
        selectedCook: deletedSelectedCook ? null : this._state.selectedCook,
        draftTags: deletedSelectedCook ? "" : this._state.draftTags,
        draftNotes: deletedSelectedCook ? "" : this._state.draftNotes,
        hoverSampleIndex: deletedSelectedCook ? null : this._state.hoverSampleIndex,
        hoverErrorIndex: deletedSelectedCook ? null : this._state.hoverErrorIndex,
      });

      if (deletedSelectedCook && nextSelectedCookId) {
        await this._loadCook(nextSelectedCookId);
      }
    } catch (err) {
      this._patchState({
        deletingCookId: null,
        error: err?.message ?? "Failed to delete cook",
      });
    }
  }

  _patchState(patch) {
    this._state = { ...this._state, ...patch };
    this._render();
  }

  _bindEvents() {
    if (this._bound) {
      return;
    }

    this.shadowRoot.addEventListener("click", (event) => {
      const cancelDeleteButton = event.target.closest(
        "[data-action='cancel-delete']",
      );
      if (cancelDeleteButton) {
        this._patchState({ confirmDeleteCookId: null });
        return;
      }

      const deleteButton = event.target.closest("[data-action='delete']");
      if (deleteButton) {
        if (this._state.confirmDeleteCookId !== deleteButton.dataset.deleteCookId) {
          this._patchState({
            confirmDeleteCookId: deleteButton.dataset.deleteCookId,
          });
          return;
        }

        this._deleteCook(deleteButton.dataset.deleteCookId);
        return;
      }

      const cookButton = event.target.closest("[data-cook-id]");
      if (cookButton) {
        this._patchState({ confirmDeleteCookId: null });
        this._loadCook(cookButton.dataset.cookId);
        return;
      }

      if (event.target.closest("[data-action='save']")) {
        this._saveAnnotations();
      }
    });

    this.shadowRoot.addEventListener("input", (event) => {
      if (event.target.matches("[name='tags']")) {
        this._patchState({ draftTags: event.target.value });
      }
      if (event.target.matches("[name='notes']")) {
        this._patchState({ draftNotes: event.target.value });
      }
    });

    this.shadowRoot.addEventListener("mousemove", (event) => {
      const chart = event.target.closest?.(".cook-chart");
      if (!chart) {
        if (this._state.hoverSampleIndex != null) {
          this._patchState({ hoverSampleIndex: null });
        }
        return;
      }

      this._updateChartHover(event, chart);
    });

    this.shadowRoot.addEventListener("mouseleave", (event) => {
      if (!event.target.matches?.(".chart-frame, .cook-chart")) {
        return;
      }

      if (this._state.hoverSampleIndex != null) {
        this._patchState({ hoverSampleIndex: null });
      }
    }, true);

    this._bound = true;
  }

  get _configEntryId() {
    return this._panel?.config?.config_entry_id ?? this._panel?.config_entry_id ?? null;
  }

  get _title() {
    return this._panel?.config?.title ?? this._panel?.title ?? "Pit Boss";
  }

  _formatTimestamp(value) {
    if (!value) {
      return "-";
    }
    return new Date(value).toLocaleString();
  }

  _formatDuration(seconds) {
    if (seconds == null) {
      return "-";
    }
    const totalMinutes = Math.round(seconds / 60);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
  }

  _getCookMinuteOffset(cook, timestamp) {
    if (!cook?.start || !timestamp) {
      return 0;
    }

    const start = new Date(cook.start).getTime();
    const current = new Date(timestamp).getTime();
    if (Number.isNaN(start) || Number.isNaN(current) || current <= start) {
      return 0;
    }

    return Math.round((current - start) / 60000);
  }

  _formatMinutesLabel(minutes) {
    const totalMinutes = Math.max(0, Math.round(minutes));
    const hours = Math.floor(totalMinutes / 60);
    const remainderMinutes = totalMinutes % 60;

    if (hours === 0) {
      return `${remainderMinutes}m`;
    }

    if (remainderMinutes === 0) {
      return `${hours}h`;
    }

    return `${hours}h ${remainderMinutes}m`;
  }

  _wrapTooltipMessage(label, value, maxLineLength = 64) {
    const normalizedValue = String(value ?? "Unknown error").trim() || "Unknown error";
    const prefix = `${label}: `;
    const continuationPrefix = " ".repeat(prefix.length);
    const words = normalizedValue.split(/\s+/);
    const lines = [];
    let currentLine = prefix;

    words.forEach((word) => {
      const candidate =
        currentLine.trim().length === 0
          ? word
          : `${currentLine}${currentLine.endsWith(" ") ? "" : " "}${word}`;

      if (candidate.length > maxLineLength && currentLine !== prefix) {
        lines.push(currentLine);
        currentLine = `${continuationPrefix}${word}`;
        return;
      }

      currentLine = candidate;
    });

    lines.push(currentLine);
    return lines;
  }

  _formatErrorTooltip(error) {
    const timingLabel = error.end ?? error.end_timestamp
      ? `${this._formatMinutesLabel(error.minutes)} to ${this._formatMinutesLabel(error.endMinutes)}`
      : this._formatMinutesLabel(error.minutes);

    const lines = [
      `Error: ${timingLabel}`,
      `Started: ${this._formatTimestamp(error.timestamp)}`,
    ];

    if (error.end ?? error.end_timestamp) {
      lines.push(`Ended: ${this._formatTimestamp(error.end ?? error.end_timestamp)}`);
    }

    lines.push(`Source: ${error.source ?? "device"}`);
    lines.push(...this._wrapTooltipMessage("Message", error.message));
    return lines.join("\n");
  }

  _getChartSeries() {
    return [
      {
        key: "grill_actual",
        label: "Smoker actual",
        color: "var(--pitboss-chart-grill-actual-color)",
        dash: "0",
      },
      {
        key: "grill_set",
        label: "Smoker target",
        color: "var(--primary-color)",
        dash: "8 6",
      },
      {
        key: "probe1_actual",
        label: "Probe 1",
        color: "var(--pitboss-chart-probe1-color)",
        dash: "0",
      },
      {
        key: "probe2_actual",
        label: "Probe 2",
        color: "var(--pitboss-chart-probe2-color)",
        dash: "0",
      },
    ];
  }

  _getStallMinimumTemperature(unit) {
    return unit === "C"
      ? STALL_MINIMUM_TEMPERATURE_C
      : STALL_MINIMUM_TEMPERATURE_F;
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

  _getStallSpans(cook, samples) {
    if (samples.length < 2) {
      return [];
    }

    if (samples.some((sample) => typeof sample.probe1_stalled === "boolean")) {
      const spans = [];
      let spanStart = null;

      samples.forEach((sample, index) => {
        const stalled = sample.probe1_stalled === true;
        if (stalled && spanStart == null) {
          spanStart = sample.minutes;
          return;
        }

        if (!stalled && spanStart != null) {
          spans.push({
            start: spanStart,
            end: samples[index].minutes,
          });
          spanStart = null;
        }
      });

      if (spanStart != null) {
        spans.push({
          start: spanStart,
          end: samples[samples.length - 1].minutes,
        });
      }

      return spans.filter((span) => span.end > span.start);
    }

    const minimumTemperature = this._getStallMinimumTemperature(cook.unit);
    const stalledFlags = samples.map((sample, index) => {
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

    const spans = [];
    let spanStart = null;

    stalledFlags.forEach((stalled, index) => {
      if (stalled && spanStart == null) {
        spanStart = samples[index].minutes;
        return;
      }

      if (!stalled && spanStart != null) {
        spans.push({
          start: spanStart,
          end: samples[index].minutes,
        });
        spanStart = null;
      }
    });

    if (spanStart != null) {
      spans.push({
        start: spanStart,
        end: samples[samples.length - 1].minutes,
      });
    }

    return spans.filter((span) => span.end > span.start);
  }

  _getChartContext(cook) {
    const rawSamples = cook?.samples ?? [];
    if (rawSamples.length === 0) {
      return null;
    }

    const plotWidth = CHART_WIDTH - CHART_PADDING.left - CHART_PADDING.right;
    const plotHeight = CHART_HEIGHT - CHART_PADDING.top - CHART_PADDING.bottom;
    const samples = rawSamples.map((sample) => ({
      ...sample,
      minutes: this._getCookMinuteOffset(cook, sample.timestamp),
    }));
    const errors = (cook?.errors ?? []).map((error) => {
      const startMinutes = this._getCookMinuteOffset(cook, error.timestamp);
      const endTimestamp = error.end ?? error.end_timestamp ?? null;
      const endMinutes = endTimestamp
        ? Math.max(startMinutes, this._getCookMinuteOffset(cook, endTimestamp))
        : startMinutes;

      return {
        ...error,
        minutes: startMinutes,
        endMinutes,
        isRange: endMinutes > startMinutes,
      };
    });
    const maxMinutes = Math.max(...samples.map((sample) => sample.minutes), 1);
    const maxTemperature = Math.max(
      ...samples.flatMap((sample) => [
        sample.grill_actual,
        sample.grill_set,
        sample.probe1_actual,
        sample.probe2_actual,
      ]),
      50,
    );
    const xAxisMax = Math.max(
      CHART_TICK_MINUTES,
      Math.ceil(maxMinutes / CHART_TICK_MINUTES) * CHART_TICK_MINUTES,
    );
    const yAxisMax = Math.ceil(maxTemperature / 25) * 25;
    const yTicks = 5;
    const xTicks = Math.max(1, xAxisMax / CHART_TICK_MINUTES);

    return {
      samples,
      errors,
      series: this._getChartSeries(),
      stallSpans: this._getStallSpans(cook, samples),
      plotWidth,
      plotHeight,
      maxMinutes: xAxisMax,
      yAxisMax,
      xTickValues: Array.from(
        { length: xTicks + 1 },
        (_value, index) => index * CHART_TICK_MINUTES,
      ),
      yTickValues: Array.from({ length: yTicks + 1 }, (_value, index) =>
        Math.round((yAxisMax / yTicks) * index),
      ),
      xForMinutes: (minutes) =>
        CHART_PADDING.left + (minutes / xAxisMax) * plotWidth,
      yForTemp: (temperature) =>
        CHART_PADDING.top + plotHeight - (temperature / yAxisMax) * plotHeight,
    };
  }

  _updateChartHover(event, chart) {
    const cook = this._state.selectedCook;
    const chartContext = this._getChartContext(cook);
    if (!cook || !chartContext) {
      return;
    }

    const rect = chart.getBoundingClientRect();
    if (!rect.width) {
      return;
    }

    const relativeX = ((event.clientX - rect.left) / rect.width) * CHART_WIDTH;
    let nextHoverSampleIndex = 0;
    let nearestDistance = Number.POSITIVE_INFINITY;

    chartContext.samples.forEach((sample, index) => {
      const distance = Math.abs(chartContext.xForMinutes(sample.minutes) - relativeX);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nextHoverSampleIndex = index;
      }
    });

    if (this._state.hoverSampleIndex !== nextHoverSampleIndex) {
      this._patchState({
        hoverSampleIndex: nextHoverSampleIndex,
      });
    }
  }

  _renderCookList() {
    if (this._state.loadingList) {
      return '<div class="empty">Loading cooks...</div>';
    }

    if (this._state.cooks.length === 0) {
      return '<div class="empty">No completed cooks yet.</div>';
    }

    return this._state.cooks
      .map((cook) => {
        const selected = cook.id === this._state.selectedCookId ? "selected" : "";
        const tags = cook.annotations?.tags ?? [];
        const deleting = cook.id === this._state.deletingCookId;
        const confirmingDelete = cook.id === this._state.confirmDeleteCookId;
        return `
          <div class="cook-item ${selected}">
            <button class="cook-item-main" data-cook-id="${escapeHtml(cook.id)}">
              <div class="cook-item-title">${escapeHtml(this._formatTimestamp(cook.start))}</div>
              <div class="cook-item-meta">${escapeHtml(this._formatDuration(cook.duration_seconds))}</div>
              ${
                tags.length
                  ? `<div class="cook-tags">${tags
                      .map((tag) => `<span class="cook-tag">${escapeHtml(tag)}</span>`)
                      .join("")}</div>`
                  : ""
              }
            </button>
            <button
              class="cook-delete ${confirmingDelete ? "is-confirming" : ""}"
              data-action="delete"
              data-delete-cook-id="${escapeHtml(cook.id)}"
              ${deleting ? "disabled" : ""}
              aria-label="Delete cook ${escapeHtml(this._formatTimestamp(cook.start))}"
            >
              ${deleting ? "Deleting..." : confirmingDelete ? "Confirm delete" : "Delete"}
            </button>
            ${
              confirmingDelete && !deleting
                ? `
                  <div class="cook-delete-confirm">
                    <span>Delete this cook permanently?</span>
                    <button class="cook-delete-cancel" data-action="cancel-delete">Cancel</button>
                  </div>
                `
                : ""
            }
          </div>
        `;
      })
      .join("");
  }

  _renderSummary(cook) {
    const summary = cook.summary ?? {};
    return `
      <div class="summary-grid">
        <div><span>Started</span><strong>${escapeHtml(this._formatTimestamp(cook.start))}</strong></div>
        <div><span>Ended</span><strong>${escapeHtml(this._formatTimestamp(cook.end))}</strong></div>
        <div><span>Duration</span><strong>${escapeHtml(this._formatDuration(cook.duration_seconds))}</strong></div>
        <div><span>Done At</span><strong>${escapeHtml(this._formatTimestamp(cook.done_at))}</strong></div>
        <div><span>Stalls</span><strong>${escapeHtml(cook.stall_count ?? 0)}</strong></div>
        <div><span>Samples</span><strong>${escapeHtml(summary.sample_count ?? 0)}</strong></div>
        <div><span>Peak Grill</span><strong>${escapeHtml(summary.peak_grill_actual ?? "-")}</strong></div>
        <div><span>Peak Probe 1</span><strong>${escapeHtml(summary.peak_probe1_actual ?? "-")}</strong></div>
        <div><span>Peak Probe 2</span><strong>${escapeHtml(summary.peak_probe2_actual ?? "-")}</strong></div>
      </div>
    `;
  }

  _renderSamples(cook) {
    const chart = this._getChartContext(cook);
    if (!chart) {
      return '<div class="empty">No samples stored for this cook.</div>';
    }

    const buildPath = (key) => {
      const points = chart.samples.map((sample) => {
        const x = chart.xForMinutes(sample.minutes);
        const y = chart.yForTemp(sample[key] ?? 0);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      });
      return points.join(" ");
    };

    const hoverSample =
      this._state.hoverSampleIndex == null
        ? null
        : chart.samples[this._state.hoverSampleIndex] ?? null;
    const displaySample = hoverSample ?? {
      minutes: null,
      grill_actual: "--",
      grill_set: "--",
      probe1_actual: "--",
      probe2_actual: "--",
    };

    return `
      <div class="chart-shell">
        <div class="chart-legend">
          ${chart.series
            .map(
              (item) => `
                <div class="legend-item">
                  <svg class="legend-swatch" viewBox="0 0 32 8" aria-hidden="true">
                    <line x1="1" y1="4" x2="31" y2="4" stroke="${item.color}" stroke-width="3" stroke-linecap="round" stroke-dasharray="${item.dash}"></line>
                  </svg>
                  <span>${escapeHtml(item.label)}</span>
                </div>
              `,
            )
            .join("")}
        </div>
        <div class="chart-frame">
          <div class="chart-scroll">
            <svg viewBox="0 0 ${CHART_WIDTH} ${CHART_HEIGHT}" class="cook-chart" role="img" aria-label="Cook temperatures over time">
            ${chart.stallSpans
              .map(
                (span) => `
                  <rect
                    x="${chart.xForMinutes(span.start).toFixed(1)}"
                    y="${CHART_PADDING.top}"
                    width="${Math.max(chart.xForMinutes(span.end) - chart.xForMinutes(span.start), 3).toFixed(1)}"
                    height="${chart.plotHeight.toFixed(1)}"
                    class="stall-band"
                  ></rect>
                `,
              )
              .join("")}
            ${chart.yTickValues
              .map((tick) => {
                const y = chart.yForTemp(tick);
                return `
                  <line x1="${CHART_PADDING.left}" y1="${y.toFixed(1)}" x2="${CHART_WIDTH - CHART_PADDING.right}" y2="${y.toFixed(1)}" class="grid-line"></line>
                  <text x="${CHART_PADDING.left - 10}" y="${(y + 4).toFixed(1)}" text-anchor="end" class="axis-label">${escapeHtml(tick)}</text>
                `;
              })
              .join("")}
            ${chart.xTickValues
              .map((tick) => {
                const x = chart.xForMinutes(tick);
                return `
                  <line x1="${x.toFixed(1)}" y1="${CHART_PADDING.top}" x2="${x.toFixed(1)}" y2="${CHART_PADDING.top + chart.plotHeight}" class="grid-line grid-line-vertical"></line>
                  <text x="${x.toFixed(1)}" y="${CHART_HEIGHT - 10}" text-anchor="middle" class="axis-label">${escapeHtml(this._formatMinutesLabel(tick))}</text>
                `;
              })
              .join("")}
            <line x1="${CHART_PADDING.left}" y1="${CHART_PADDING.top + chart.plotHeight}" x2="${CHART_WIDTH - CHART_PADDING.right}" y2="${CHART_PADDING.top + chart.plotHeight}" class="axis-line"></line>
            <line x1="${CHART_PADDING.left}" y1="${CHART_PADDING.top}" x2="${CHART_PADDING.left}" y2="${CHART_PADDING.top + chart.plotHeight}" class="axis-line"></line>
            ${chart.series
              .map(
                (item) => `
                  <polyline
                    fill="none"
                    stroke="${item.color}"
                    stroke-width="3"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-dasharray="${item.dash}"
                    points="${buildPath(item.key)}"
                  ></polyline>
                `,
              )
              .join("")}
            ${chart.errors
              .map(
                (error) => `
                  <g class="chart-error-marker">
                    <title>${escapeHtml(this._formatErrorTooltip(error))}</title>
                    ${
                      error.isRange
                        ? `
                          <line
                            x1="${chart.xForMinutes(error.minutes).toFixed(1)}"
                            y1="${(CHART_PADDING.top + 12).toFixed(1)}"
                            x2="${chart.xForMinutes(error.endMinutes).toFixed(1)}"
                            y2="${(CHART_PADDING.top + 12).toFixed(1)}"
                            class="error-marker-range"
                          ></line>
                        `
                        : ""
                    }
                    <line
                      x1="${chart.xForMinutes(error.minutes).toFixed(1)}"
                      y1="${CHART_PADDING.top}"
                      x2="${chart.xForMinutes(error.minutes).toFixed(1)}"
                      y2="${(CHART_PADDING.top + 22).toFixed(1)}"
                      class="error-marker-stem"
                    ></line>
                    <circle
                      cx="${chart.xForMinutes(error.minutes).toFixed(1)}"
                      cy="${(CHART_PADDING.top + 12).toFixed(1)}"
                      r="10"
                      class="error-marker-hitbox"
                      aria-hidden="true"
                    ></circle>
                    <circle
                      cx="${chart.xForMinutes(error.minutes).toFixed(1)}"
                      cy="${(CHART_PADDING.top + 12).toFixed(1)}"
                      r="4.5"
                      class="error-marker-dot"
                    ></circle>
                    ${
                      error.isRange
                        ? `
                          <line
                            x1="${chart.xForMinutes(error.endMinutes).toFixed(1)}"
                            y1="${CHART_PADDING.top}"
                            x2="${chart.xForMinutes(error.endMinutes).toFixed(1)}"
                            y2="${(CHART_PADDING.top + 22).toFixed(1)}"
                            class="error-marker-stem"
                          ></line>
                          <circle
                            cx="${chart.xForMinutes(error.endMinutes).toFixed(1)}"
                            cy="${(CHART_PADDING.top + 12).toFixed(1)}"
                            r="10"
                            class="error-marker-hitbox"
                            aria-hidden="true"
                          ></circle>
                          <circle
                            cx="${chart.xForMinutes(error.endMinutes).toFixed(1)}"
                            cy="${(CHART_PADDING.top + 12).toFixed(1)}"
                            r="4.5"
                            class="error-marker-dot"
                          ></circle>
                        `
                        : ""
                    }
                  </g>
                `,
              )
              .join("")}
            <text x="${CHART_PADDING.left}" y="14" class="axis-title">Temperature</text>
            ${
              hoverSample
                ? `
                  <line
                    x1="${chart.xForMinutes(hoverSample.minutes).toFixed(1)}"
                    y1="${CHART_PADDING.top}"
                    x2="${chart.xForMinutes(hoverSample.minutes).toFixed(1)}"
                    y2="${CHART_PADDING.top + chart.plotHeight}"
                    class="hover-line"
                  ></line>
                  ${chart.series
                    .map(
                      (item) => `
                        <circle
                          cx="${chart.xForMinutes(hoverSample.minutes).toFixed(1)}"
                          cy="${chart.yForTemp(hoverSample[item.key]).toFixed(1)}"
                          r="4.5"
                          fill="${item.color}"
                          class="hover-point"
                        ></circle>
                      `,
                    )
                    .join("")}
                `
                : ""
            }
            </svg>
          </div>
        </div>
        <div class="chart-hover ${hoverSample ? "" : "idle"}">
          <div class="chart-hover-time-pill">
            <span class="chart-hover-time-label">Time</span>
            <strong class="chart-hover-time">${escapeHtml(
              displaySample.minutes == null
                ? "--"
                : this._formatMinutesLabel(displaySample.minutes),
            )}</strong>
          </div>
          <div class="chart-hover-chip chart-hover-chip-grill-actual">
            <span class="chart-hover-chip-label">Smoker actual</span>
            <strong>${escapeHtml(displaySample.grill_actual)}</strong>
          </div>
          <div class="chart-hover-chip chart-hover-chip-grill-set">
            <span class="chart-hover-chip-label">Smoker target</span>
            <strong>${escapeHtml(displaySample.grill_set)}</strong>
          </div>
          <div class="chart-hover-chip chart-hover-chip-probe1">
            <span class="chart-hover-chip-label">Probe 1</span>
            <strong>${escapeHtml(displaySample.probe1_actual)}</strong>
          </div>
          <div class="chart-hover-chip chart-hover-chip-probe2">
            <span class="chart-hover-chip-label">Probe 2</span>
            <strong>${escapeHtml(displaySample.probe2_actual)}</strong>
          </div>
        </div>
      </div>
    `;
  }

  _renderErrors(cook) {
    const errors = cook.errors ?? [];
    if (errors.length === 0) {
      return '<div class="subtle">No cook errors were recorded.</div>';
    }

    return `
      <div class="cook-error-list">
        ${errors
          .map(
            (error) => `
              <article class="cook-error-item">
                <div class="cook-error-meta">
                  <strong>${escapeHtml(this._formatTimestamp(error.timestamp))}</strong>
                  <span>${escapeHtml(error.source ?? "device")}</span>
                </div>
                <div class="cook-error-message">${escapeHtml(error.message ?? "Unknown error")}</div>
              </article>
            `,
          )
          .join("")}
      </div>
    `;
  }

  _renderDetail() {
    if (!this._configEntryId) {
      return `
        <div class="detail">
          <ha-card class="detail-card">
            <div class="card-content empty">This panel is missing its config entry context.</div>
          </ha-card>
        </div>
      `;
    }

    if (this._state.loadingCook) {
      return `
        <div class="detail">
          <ha-card class="detail-card">
            <div class="card-content empty">Loading cook details...</div>
          </ha-card>
        </div>
      `;
    }

    const cook = this._state.selectedCook;
    if (!cook) {
      return `
        <div class="detail">
          <ha-card class="detail-card">
            <div class="card-content empty">Select a cook to view details.</div>
          </ha-card>
        </div>
      `;
    }

    return `
      <div class="detail">
        <ha-card class="detail-card">
          <div class="card-content">
            <h2>Summary</h2>
            ${this._renderSummary(cook)}
          </div>
        </ha-card>
        <ha-card class="detail-card">
          <div class="card-content">
            <h2>Annotations</h2>
            <label>
              <span class="field-label">Tags</span>
              <input name="tags" value="${escapeHtml(this._state.draftTags)}" placeholder="brisket, overnight" />
            </label>
            <label>
              <span class="field-label">Notes</span>
              <textarea name="notes" rows="5" placeholder="Wrap time, bark notes, weather...">${escapeHtml(this._state.draftNotes)}</textarea>
            </label>
            <div class="card-actions">
              <button class="save" data-action="save" ${this._state.saving ? "disabled" : ""}>
                ${this._state.saving ? "Saving..." : "Save annotations"}
              </button>
            </div>
          </div>
        </ha-card>
        <ha-card class="detail-card detail-card-chart">
          <div class="card-content">
            <h2>Temperature graph</h2>
            ${this._renderSamples(cook)}
          </div>
        </ha-card>
        <ha-card class="detail-card">
          <div class="card-content">
            <h2>Cook errors</h2>
            ${this._renderErrors(cook)}
          </div>
        </ha-card>
      </div>
    `;
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          --pitboss-chart-grill-actual-color: var(--warning-color, var(--accent-color));
          --pitboss-chart-grill-set-color: var(--primary-color);
          --pitboss-chart-probe1-color: var(--error-color);
          --pitboss-chart-probe2-color: var(--info-color, var(--accent-color));
          --pitboss-chart-stall-color: color-mix(
            in srgb,
            var(--pitboss-chart-grill-actual-color) 14%,
            transparent
          );
          display: block;
          padding: 24px;
          color: var(--primary-text-color);
        }
        .layout {
          display: grid;
          gap: 24px;
          grid-template-columns: minmax(260px, 320px) 1fr;
        }
        .panel,
        .detail,
        ha-card {
          box-sizing: border-box;
        }
        .detail {
          display: grid;
          gap: 16px;
        }
        .card-content {
          padding: 16px;
        }
        .card-actions {
          display: flex;
          justify-content: flex-end;
          margin-top: 12px;
        }
        h1,
        h2 {
          margin: 0 0 12px;
        }
        h1 {
          font-size: 1.7rem;
        }
        h2 {
          font-size: 1.1rem;
        }
        .cook-list {
          display: grid;
          gap: 10px;
        }
        .cook-item {
          align-items: stretch;
          background: transparent;
          border: 1px solid var(--divider-color);
          border-radius: 12px;
          display: grid;
          gap: 10px;
          grid-template-columns: 1fr auto;
          padding: 12px;
        }
        .cook-item-main {
          background: transparent;
          border: 0;
          color: inherit;
          cursor: pointer;
          padding: 0;
          text-align: left;
        }
        .cook-item.selected {
          border-color: var(--primary-color);
          box-shadow: inset 0 0 0 1px var(--primary-color);
        }
        .cook-delete {
          align-self: start;
          background: var(--secondary-background-color);
          border: 1px solid var(--divider-color);
          border-radius: 999px;
          color: var(--secondary-text-color);
          cursor: pointer;
          font: inherit;
          padding: 8px 12px;
        }
        .cook-delete.is-confirming {
          background: color-mix(in srgb, var(--error-color) 8%, var(--secondary-background-color));
          border-color: color-mix(in srgb, var(--error-color) 28%, var(--divider-color));
          color: var(--error-color);
        }
        .cook-delete[disabled] {
          cursor: wait;
          opacity: 0.7;
        }
        .cook-delete-confirm {
          align-items: center;
          color: var(--secondary-text-color);
          display: flex;
          gap: 10px;
          grid-column: 1 / -1;
          justify-content: space-between;
          padding-top: 2px;
        }
        .cook-delete-cancel {
          background: transparent;
          border: 0;
          color: var(--primary-color);
          cursor: pointer;
          font: inherit;
          padding: 0;
        }
        .cook-item-title {
          font-weight: 600;
          margin-bottom: 4px;
        }
        .cook-item-meta,
        .subtle,
        .field-label {
          color: var(--secondary-text-color);
          font-size: 0.92rem;
        }
        .summary-grid {
          display: grid;
          gap: 12px;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        }
        .summary-grid span,
        .field-label {
          display: block;
          margin-bottom: 4px;
        }
        .summary-grid strong {
          display: block;
          font-size: 1rem;
        }
        label {
          display: block;
          margin-bottom: 12px;
        }
        .cook-tags {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-top: 10px;
        }
        .cook-tag {
          background: color-mix(in srgb, var(--primary-color) 16%, transparent);
          border-radius: 999px;
          font-size: 0.8rem;
          padding: 3px 8px;
        }
        input,
        textarea {
          background: var(--secondary-background-color);
          border: 1px solid var(--divider-color);
          border-radius: 10px;
          box-sizing: border-box;
          color: inherit;
          font: inherit;
          padding: 10px 12px;
          width: 100%;
        }
        .save {
          background: var(--primary-color);
          border: 0;
          border-radius: 999px;
          color: var(--text-primary-color, white);
          cursor: pointer;
          font: inherit;
          padding: 10px 16px;
        }
        .save[disabled] {
          cursor: wait;
          opacity: 0.7;
        }
        .chart-shell {
          display: grid;
          gap: 16px;
        }
        .chart-legend {
          display: flex;
          flex-wrap: wrap;
          gap: 10px 16px;
        }
        .legend-item {
          align-items: center;
          display: inline-flex;
          gap: 8px;
          font-size: 0.92rem;
        }
        .legend-swatch {
          display: block;
          height: 8px;
          width: 32px;
        }
        .chart-frame {
          position: relative;
        }
        .chart-scroll {
          overflow-x: auto;
        }
        .cook-chart {
          display: block;
          height: auto;
          min-width: 640px;
          width: 100%;
        }
        .grid-line {
          stroke: color-mix(in srgb, var(--divider-color) 80%, transparent);
          stroke-width: 1;
        }
        .stall-band {
          fill: var(--pitboss-chart-stall-color);
        }
        .grid-line-vertical {
          stroke-dasharray: 4 6;
        }
        .axis-line {
          stroke: var(--secondary-text-color);
          stroke-width: 1.5;
        }
        .hover-line {
          stroke: color-mix(in srgb, var(--primary-color) 55%, transparent);
          stroke-dasharray: 4 6;
          stroke-width: 2;
        }
        .hover-point {
          stroke: var(--card-background-color);
          stroke-width: 2;
        }
        .error-marker-stem {
          stroke: color-mix(in srgb, var(--error-color) 55%, transparent);
          stroke-width: 2;
          stroke-dasharray: 3 4;
          pointer-events: none;
        }
        .error-marker-range {
          stroke: color-mix(in srgb, var(--error-color) 70%, transparent);
          stroke-linecap: round;
          stroke-width: 3;
          pointer-events: none;
        }
        .error-marker-hitbox {
          fill: transparent;
          cursor: pointer;
        }
        .error-marker-dot {
          fill: var(--error-color);
          stroke: var(--card-background-color);
          stroke-width: 2;
          transition: stroke-width 120ms ease, filter 120ms ease;
        }
        .chart-error-marker:hover .error-marker-dot,
        .chart-error-marker:focus-within .error-marker-dot {
          filter: drop-shadow(0 0 4px color-mix(in srgb, var(--error-color) 45%, transparent));
          stroke-width: 3;
        }
        .axis-label,
        .axis-title {
          fill: var(--secondary-text-color);
          font-family: inherit;
          font-size: 13px;
        }
        .chart-hover {
          align-items: stretch;
          background: color-mix(in srgb, var(--card-background-color) 92%, black);
          border: 1px solid var(--divider-color);
          border-radius: 14px;
          box-sizing: border-box;
          display: grid;
          gap: 12px;
          grid-template-columns: repeat(5, minmax(0, 1fr));
          min-height: 52px;
          font-size: 0.92rem;
          padding: 8px 12px;
          width: 100%;
        }
        .chart-hover.idle {
          opacity: 0.92;
        }
        .chart-error-tooltip {
          background: color-mix(in srgb, var(--error-color) 10%, var(--card-background-color));
          border: 1px solid color-mix(in srgb, var(--error-color) 24%, var(--divider-color));
          border-radius: 14px;
          box-shadow: 0 12px 28px rgba(0, 0, 0, 0.22);
          display: grid;
          gap: 6px;
          max-width: min(320px, calc(100% - 24px));
          min-width: 220px;
          pointer-events: none;
          padding: 12px 14px;
          position: absolute;
          transform: translate(-50%, 0);
          z-index: 3;
        }
        .chart-error-hover-head,
        .chart-error-hover-meta {
          align-items: baseline;
          display: flex;
          gap: 10px;
          justify-content: space-between;
        }
        .chart-error-hover-head strong {
          color: var(--error-color);
        }
        .chart-error-hover-head span,
        .chart-error-hover-meta {
          color: var(--secondary-text-color);
          font-size: 0.86rem;
        }
        .chart-error-hover-message {
          color: var(--primary-text-color);
          font-size: 0.95rem;
        }
        .chart-hover-time-pill,
        .chart-hover-chip {
          align-items: center;
          background: color-mix(in srgb, var(--card-background-color) 88%, white 3%);
          border: 1px solid var(--divider-color);
          border-radius: 999px;
          box-sizing: border-box;
          display: inline-flex;
          justify-content: space-between;
          gap: 8px;
          min-height: 36px;
          min-width: 0;
          overflow: hidden;
          padding: 0 10px;
          width: 100%;
        }
        .chart-hover-time-pill {
          background: color-mix(in srgb, var(--primary-color) 10%, var(--card-background-color));
        }
        .chart-hover-time-label,
        .chart-hover-chip-label {
          color: var(--secondary-text-color);
          font-size: 0.82rem;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .chart-hover-time {
          color: var(--primary-text-color);
          font-size: 0.96rem;
          font-weight: 700;
        }
        .chart-hover-chip {
          background: color-mix(in srgb, var(--hover-chip-color) 10%, var(--card-background-color));
          border-color: color-mix(in srgb, var(--hover-chip-color) 28%, var(--divider-color));
        }
        .chart-hover-chip strong {
          color: var(--hover-chip-color);
          font-size: 0.94rem;
          line-height: 1;
          flex: 0 0 auto;
        }
        .chart-hover-chip-grill-actual {
          --hover-chip-color: var(--pitboss-chart-grill-actual-color);
        }
        .chart-hover-chip-grill-set {
          --hover-chip-color: var(--pitboss-chart-grill-set-color);
        }
        .chart-hover-chip-probe1 {
          --hover-chip-color: var(--pitboss-chart-probe1-color);
        }
        .chart-hover-chip-probe2 {
          --hover-chip-color: var(--pitboss-chart-probe2-color);
        }
        .empty,
        .error {
          padding: 12px 0;
        }
        .cook-error-list {
          display: grid;
          gap: 10px;
        }
        .cook-error-item {
          background: color-mix(in srgb, var(--error-color) 8%, var(--card-background-color));
          border: 1px solid color-mix(in srgb, var(--error-color) 18%, var(--divider-color));
          border-radius: 12px;
          display: grid;
          gap: 6px;
          padding: 12px;
        }
        .cook-error-meta {
          align-items: baseline;
          color: var(--secondary-text-color);
          display: flex;
          gap: 10px;
          justify-content: space-between;
        }
        .cook-error-message {
          color: var(--primary-text-color);
          font-size: 0.95rem;
        }
        .error {
          color: var(--error-color);
        }
        @media (max-width: 960px) {
          .layout {
            grid-template-columns: 1fr;
          }
          .chart-hover {
            grid-template-columns: repeat(3, minmax(0, 1fr));
            min-height: 100px;
          }
        }
        @media (max-width: 760px) {
          .chart-hover {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            min-height: 0;
          }
          .chart-hover-time-pill {
            grid-column: 1 / -1;
          }
        }
        @media (max-width: 520px) {
          .chart-hover {
            grid-template-columns: 1fr;
            min-height: 0;
          }
        }
      </style>
      <div class="layout">
        <aside class="panel">
          <ha-card class="panel-card">
            <div class="card-content">
              <h1>${escapeHtml(this._title)}</h1>
              <div class="subtle">Cook archive</div>
              ${this._state.error ? `<div class="error">${escapeHtml(this._state.error)}</div>` : ""}
              <div class="cook-list">${this._renderCookList()}</div>
            </div>
          </ha-card>
        </aside>
        ${this._renderDetail()}
      </div>
    `;
    this._bindEvents();
  }
}

if (!customElements.get("pitboss-cook-panel")) {
  customElements.define("pitboss-cook-panel", PitbossCookPanel);
}