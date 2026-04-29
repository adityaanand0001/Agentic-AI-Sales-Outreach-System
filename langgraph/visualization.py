"""Visualization and monitoring for LangGraph workflows."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
import networkx as nx
from langgraph.graph import StateGraph

logger = logging.getLogger(__name__)


class WorkflowVisualizer:
    """Visualize and monitor LangGraph workflows."""

    def __init__(self, workflow: StateGraph):
        self.workflow = workflow
        self.compiled = workflow.compile()

    def generate_mermaid_diagram(self) -> str:
        """Generate Mermaid.js diagram of the workflow."""
        # Extract nodes and edges from the workflow
        nodes = list(self.workflow.nodes)
        edges = []

        # This is a simplified representation
        # In a real implementation, we'd traverse the graph structure
        mermaid = """graph TD
    Start[Start] --> Discover[Discover Leads]
    Discover --> Prioritize[Prioritize Lead]
    Prioritize --> Generate[Generate Email]

    Generate --> Quality[Quality Check]
    Quality --> Decision[Make Decision]

    Decision -->|Auto-send| Complete[Complete]
    Decision -->|Human Review| Complete
    Decision -->|Skip| Complete

    Complete --> End[End]

    style Start fill:#4CAF50
    style End fill:#F44336
    style Complete fill:#FFC107
    style AutoSend fill:#2196F3
    style HumanReview fill:#9C27B0
"""

        return mermaid

    def generate_networkx_graph(self) -> nx.DiGraph:
        """Generate NetworkX graph representation."""
        G = nx.DiGraph()

        # Add nodes
        nodes = [
            "Start",
            "Discover",
            "Prioritize",
            "Generate",
            "Quality",
            "Decision",
            "Complete",
            "End",
        ]

        for node in nodes:
            G.add_node(node)

        # Add edges
        edges = [
            ("Start", "Discover"),
            ("Discover", "Prioritize"),
            ("Prioritize", "Generate"),
            ("Generate", "Quality"),
            ("Quality", "Decision"),
            ("Decision", "Complete"),   # All decision paths
            ("Complete", "End"),
        ]

        for u, v in edges:
            G.add_edge(u, v)

        return G

    def plot_workflow(self, output_path: Optional[str] = None) -> None:
        """Plot workflow graph using matplotlib."""
        try:
            G = self.generate_networkx_graph()

            plt.figure(figsize=(12, 8))

            # Use spring layout
            pos = nx.spring_layout(G, seed=42)

            # Draw nodes
            node_colors = []
            for node in G.nodes():
                if node in ["Start", "End"]:
                    node_colors.append("#4CAF50" if node == "Start" else "#F44336")
                elif node == "Complete":
                    node_colors.append("#FFC107")
                else:
                    node_colors.append("#2196F3")

            nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=2000, alpha=0.8)

            # Draw edges
            nx.draw_networkx_edges(G, pos, width=2, alpha=0.5, edge_color="gray", arrows=True)

            # Draw labels
            nx.draw_networkx_labels(G, pos, font_size=10, font_weight="bold")

            # Add title
            plt.title("Mailing Agent Workflow", fontsize=16, fontweight="bold")
            plt.axis("off")

            if output_path:
                plt.savefig(output_path, dpi=300, bbox_inches="tight")
                logger.info(f"Workflow plot saved to {output_path}")
            else:
                plt.show()

            plt.close()

        except Exception as e:
            logger.error(f"Failed to plot workflow: {e}")
            raise

    def generate_execution_report(self, execution_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate execution report from workflow runs."""
        if not execution_data:
            return {"error": "No execution data provided"}

        try:
            total_executions = len(execution_data)
            successful = sum(1 for d in execution_data if d.get("status") == "COMPLETED")
            failed = total_executions - successful

            # Extract stage durations
            stage_durations = {}
            stage_counts = {}

            for exec_data in execution_data:
                if "result" in exec_data:
                    result = exec_data["result"]
                    stage = result.get("processing_stage", "UNKNOWN")
                    processing_time = result.get("processing_time", 0)

                    if stage not in stage_durations:
                        stage_durations[stage] = []
                        stage_counts[stage] = 0

                    stage_durations[stage].append(processing_time)
                    stage_counts[stage] += 1

            # Calculate averages
            avg_stage_durations = {}
            for stage, durations in stage_durations.items():
                avg_stage_durations[stage] = sum(durations) / len(durations)

            # Extract actions
            actions = []
            for exec_data in execution_data:
                if "result" in exec_data:
                    action = exec_data["result"].get("action_taken")
                    if action:
                        actions.append(action)

            action_counts = {}
            for action in actions:
                action_counts[action] = action_counts.get(action, 0) + 1

            # Extract confidence scores
            confidences = []
            for exec_data in execution_data:
                if "result" in exec_data:
                    conf = exec_data["result"].get("ai_confidence")
                    if conf is not None:
                        confidences.append(conf)

            avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            return {
                "report_generated": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "total_executions": total_executions,
                    "successful": successful,
                    "failed": failed,
                    "success_rate": (successful / total_executions * 100) if total_executions > 0 else 0,
                },
                "stage_analysis": {
                    "stage_counts": stage_counts,
                    "avg_stage_durations": avg_stage_durations,
                },
                "action_analysis": {
                    "action_counts": action_counts,
                    "total_actions": len(actions),
                },
                "ai_analysis": {
                    "avg_confidence": round(avg_confidence, 3),
                    "total_decisions": len(confidences),
                    "confidence_distribution": self._calculate_confidence_distribution(confidences),
                },
                "performance_metrics": {
                    "total_processing_time": sum(sum(durations) for durations in stage_durations.values()),
                    "avg_execution_time": sum(
                        exec_data.get("result", {}).get("processing_time", 0)
                        for exec_data in execution_data
                    ) / total_executions if total_executions > 0 else 0,
                },
            }

        except Exception as e:
            logger.error(f"Failed to generate execution report: {e}")
            return {"error": str(e)}

    def _calculate_confidence_distribution(self, confidences: List[float]) -> Dict[str, int]:
        """Calculate confidence score distribution."""
        distribution = {
            "very_low": 0,    # 0-0.2
            "low": 0,         # 0.2-0.4
            "medium": 0,      # 0.4-0.6
            "high": 0,        # 0.6-0.8
            "very_high": 0,   # 0.8-1.0
        }

        for conf in confidences:
            if conf <= 0.2:
                distribution["very_low"] += 1
            elif conf <= 0.4:
                distribution["low"] += 1
            elif conf <= 0.6:
                distribution["medium"] += 1
            elif conf <= 0.8:
                distribution["high"] += 1
            else:
                distribution["very_high"] += 1

        return distribution

    def plot_performance_metrics(self, execution_data: List[Dict[str, Any]], output_path: Optional[str] = None) -> None:
        """Plot performance metrics from execution data."""
        try:
            report = self.generate_execution_report(execution_data)
            if "error" in report:
                logger.error(f"Cannot plot metrics: {report['error']}")
                return

            fig, axes = plt.subplots(2, 2, figsize=(15, 12))

            # 1. Success/Failure Pie Chart
            ax1 = axes[0, 0]
            success_rate = report["summary"]["success_rate"]
            labels = ["Successful", "Failed"]
            sizes = [success_rate, 100 - success_rate]
            colors = ["#4CAF50", "#F44336"]
            ax1.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
            ax1.set_title("Execution Success Rate")

            # 2. Action Distribution Bar Chart
            ax2 = axes[0, 1]
            action_counts = report["action_analysis"]["action_counts"]
            if action_counts:
                actions = list(action_counts.keys())
                counts = list(action_counts.values())
                colors = ["#2196F3", "#9C27B0", "#FF9800", "#795548"]
                ax2.bar(actions, counts, color=colors[:len(actions)])
                ax2.set_title("Action Distribution")
                ax2.set_ylabel("Count")
                ax2.tick_params(axis='x', rotation=45)

            # 3. Confidence Distribution
            ax3 = axes[1, 0]
            conf_dist = report["ai_analysis"]["confidence_distribution"]
            categories = list(conf_dist.keys())
            values = list(conf_dist.values())
            colors = ["#F44336", "#FF9800", "#FFC107", "#4CAF50", "#2196F3"]
            ax3.bar(categories, values, color=colors)
            ax3.set_title("AI Confidence Distribution")
            ax3.set_ylabel("Count")
            ax3.tick_params(axis='x', rotation=45)

            # 4. Stage Duration Heatmap (simplified)
            ax4 = axes[1, 1]
            stage_durations = report["stage_analysis"]["avg_stage_durations"]
            if stage_durations:
                stages = list(stage_durations.keys())
                durations = list(stage_durations.values())
                colors = plt.cm.viridis([d / max(durations) for d in durations]) if durations else []
                bars = ax4.bar(stages, durations, color=colors)
                ax4.set_title("Average Stage Duration (seconds)")
                ax4.set_ylabel("Seconds")
                ax4.tick_params(axis='x', rotation=45)

                # Add value labels
                for bar in bars:
                    height = bar.get_height()
                    ax4.text(bar.get_x() + bar.get_width()/2., height,
                            f'{height:.2f}s', ha='center', va='bottom')

            plt.suptitle("Workflow Performance Metrics", fontsize=16, fontweight="bold")
            plt.tight_layout()

            if output_path:
                plt.savefig(output_path, dpi=300, bbox_inches="tight")
                logger.info(f"Performance metrics plot saved to {output_path}")
            else:
                plt.show()

            plt.close()

        except Exception as e:
            logger.error(f"Failed to plot performance metrics: {e}")
            raise