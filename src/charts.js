import * as echarts from "echarts/core";
import { BarChart, LineChart, PieChart, GraphChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  AriaComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GraphChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  AriaComponent,
  CanvasRenderer,
]);

export function charts({ selectReport } = {}) {
  const timeline = echarts.init(document.querySelector("#timeline-chart"));
  let sentiment;
  let discussion, discussionData;
  let history = [],
    sentimentResult = null;
  let light = false;
  const palette = () => ({
    text: light ? "#50646f" : "#99abb5",
    grid: light ? "#cad5dc" : "#2b3941",
  });
  function drawTimeline() {
    const { text, grid } = palette();
    const totals = new Map();
    for (const item of history)
      totals.set(item.time, (totals.get(item.time) || 0) + item.count);
    const entries = [...totals.entries()].sort((a, b) =>
      a[0].localeCompare(b[0]),
    );
    const trend = sentimentResult?.trend || [];
    timeline.setOption(
      {
        animation: false,
        aria: { enabled: true },
        grid: { left: 38, right: 40, top: 18, bottom: 26 },
        tooltip: { trigger: "axis", renderMode: "richText" },
        xAxis: {
          type: "category",
          data: entries.map((entry) => entry[0]),
          axisLine: { lineStyle: { color: grid } },
          axisLabel: {
            color: text,
            fontSize: 9,
            formatter: (value) =>
              value.slice(5, 10) +
              (value.length > 10 ? " " + value.slice(11, 16) : ""),
          },
          axisTick: { show: false },
        },
        yAxis: [
          {
            type: "value",
            minInterval: 1,
            axisLabel: { color: text, fontSize: 9 },
            splitLine: { lineStyle: { color: grid, type: "dashed" } },
          },
          {
            type: "value",
            min: -1,
            max: 1,
            axisLabel: { color: text, fontSize: 9 },
            splitLine: { show: false },
          },
        ],
        series: [
          {
            name: "Events",
            type: "bar",
            data: entries.map((entry) => entry[1]),
            itemStyle: { color: "#72b8a5" },
            barMaxWidth: 20,
          },
          {
            name: "Daily mean wording sentiment",
            type: "line",
            yAxisIndex: 1,
            connectNulls: false,
            showSymbol: false,
            data: entries.map(
              ([time]) =>
                trend.find((point) => point.date === time.slice(0, 10))
                  ?.score ?? null,
            ),
            itemStyle: { color: "#d5b78b" },
            lineStyle: { width: 1.5 },
          },
        ],
      },
      true,
    );
  }
  function drawSentiment() {
    if (!sentimentResult) return;
    const container = document.querySelector("#sentiment-chart");
    if (!container.clientWidth) return;
    sentiment ??= echarts.init(container);
    const { text } = palette();
    sentiment.setOption(
      {
        animation: false,
        aria: { enabled: true },
        tooltip: { trigger: "item", renderMode: "richText" },
        legend: {
          bottom: 0,
          textStyle: { color: text, fontSize: 10 },
          itemWidth: 9,
          itemHeight: 9,
        },
        color: ["#77c6a6", "#d18f7c", "#8195a1"],
        series: [
          {
            type: "pie",
            radius: ["42%", "65%"],
            center: ["50%", "43%"],
            label: { show: false },
            data: Object.entries(sentimentResult.distribution).map(
              ([name, value]) => ({ name, value }),
            ),
          },
        ],
      },
      true,
    );
  }
  function drawDiscussion() {
    const container = document.querySelector("#social-network-chart");
    if (!container.clientWidth || !discussionData?.edges.length) return;
    if (!discussion) {
      discussion = echarts.init(container);
      discussion.on("click", (params) => {
        if (params.data.report_id) selectReport?.(params.data.report_id);
      });
    }
    const color = {
      positive: "#77c6a6",
      negative: "#d18f7c",
      neutral: "#8195a1",
    };
    const linkedIds = new Set(
      discussionData.edges.flatMap((edge) => [edge.source, edge.target]),
    );
    const compact = linkedIds.size > 10;
    discussion.setOption(
      {
        animation: false,
        aria: {
          enabled: true,
          label: {
            description: `${linkedIds.size} linked public posts and ${discussionData.edges.length} explicit discussion relationships. Arrows join comments to the referenced thread or reply. Select a node to inspect its source post.`,
          },
        },
        tooltip: {
          renderMode: "richText",
          formatter: (params) =>
            params.data.name ||
            (params.data.kind === "reply"
              ? "Reply: comment → referenced comment"
              : "Comment → original thread"),
        },
        series: [
          {
            type: "graph",
            layout: compact ? "force" : "circular",
            force: {
              repulsion: 70,
              edgeLength: [30, 75],
              gravity: 0.1,
              layoutAnimation: false,
            },
            roam: true,
            edgeSymbol: ["none", "arrow"],
            edgeSymbolSize: 5,
            label: {
              show: true,
              position: "bottom",
              color: palette().text,
              fontSize: 10,
              formatter: ({ data }) =>
                data.id.startsWith("reddit:t1_") ? "Comment" : "Thread",
            },
            data: discussionData.nodes
              .filter((node) => linkedIds.has(node.id))
              .map((node) => ({
                ...node,
                symbolSize: compact
                  ? node.id.startsWith("reddit:t3_")
                    ? 18
                    : 9
                  : node.in_sample
                    ? 18
                    : 24,
                itemStyle: { color: color[node.label] || "#657884" },
                label: {
                  show: !compact || node.id.startsWith("reddit:t3_"),
                },
              })),
            links: discussionData.edges,
            lineStyle: {
              color: "#99abb5",
              opacity: 0.75,
              width: 1.5,
              curveness: 0.15,
            },
            emphasis: {
              focus: "adjacency",
              lineStyle: { opacity: 1, width: 2 },
              label: { show: true },
            },
          },
        ],
      },
      true,
    );
    discussion.resize();
  }
  const resize = new ResizeObserver(() => {
    timeline.resize();
    drawSentiment();
    sentiment?.resize();
    drawDiscussion();
  });
  resize.observe(document.querySelector("#timeline-chart"));
  resize.observe(document.querySelector("#sentiment-chart"));
  resize.observe(document.querySelector("#social-network-chart"));
  return {
    setTimeline(items) {
      history = items;
      drawTimeline();
    },
    setSentiment(result) {
      sentimentResult = result;
      drawSentiment();
      drawTimeline();
    },
    setDiscussionNetwork(result) {
      discussionData = result;
      drawDiscussion();
    },
    setTheme(value) {
      light = value;
      drawTimeline();
      drawSentiment();
      drawDiscussion();
    },
    resize() {
      timeline.resize();
      drawSentiment();
      sentiment?.resize();
      drawDiscussion();
    },
  };
}
