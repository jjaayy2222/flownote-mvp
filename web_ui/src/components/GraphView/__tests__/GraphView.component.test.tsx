import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GRAPH_HIGHLIGHT_COLOR } from '@/config/graph';
import { EdgeRelationshipType, NodeType } from '@/types/websocket';
import type { GraphEdge, GraphNode } from '@/types/websocket';
import { GraphContainer } from '../GraphContainer';
import { GraphView } from '../GraphView';
import type { GraphViewData } from '../types';
import type { OnLinkClickCallback } from '..';

const mocks = vi.hoisted(() => ({
  graphData: null as GraphViewData | null,
  loading: true,
  reload: vi.fn(),
  isConnected: false,
  context: {
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    save: vi.fn(),
    stroke: vi.fn(),
    restore: vi.fn(),
    fillText: vi.fn(),
    fillStyle: '',
    font: '',
    lineWidth: 1,
    strokeStyle: '',
    textAlign: 'center',
    textBaseline: 'top',
  },
}));

vi.mock('react-force-graph-2d', async () => {
  const React = await import('react');

  const ForceGraph2D = (props: Record<string, unknown>) => {
    const graphData = props.graphData as {
      nodes: Array<{ id: string; label: string }>;
      links: Array<{ id: string; source: string | { id: string }; target: string | { id: string } }>;
    };
    const onNodeClick = props.onNodeClick as ((node: unknown) => void) | undefined;
    const onLinkClick = props.onLinkClick as ((link: unknown) => void) | undefined;
    const nodeCanvasObject = props.nodeCanvasObject as (
      node: unknown,
      context: CanvasRenderingContext2D,
    ) => void;
    const [paintedColor, setPaintedColor] = React.useState('');

    const paintFirstNode = () => {
      const node = graphData.nodes[0];
      if (!node) return;
      nodeCanvasObject(node, mocks.context as unknown as CanvasRenderingContext2D);
      setPaintedColor(mocks.context.fillStyle);
    };

    return (
      <div data-testid="force-graph">
        <ul aria-label="Graph nodes">
          {graphData.nodes.map((node) => <li key={node.id}>{node.label}</li>)}
        </ul>
        <output data-testid="graph-links">
          {graphData.links.map((link) => {
            const source = typeof link.source === 'string' ? link.source : link.source.id;
            const target = typeof link.target === 'string' ? link.target : link.target.id;
            return `${link.id}:${source}->${target}`;
          }).join(',')}
        </output>
        <output data-testid="painted-node-color">{paintedColor}</output>
        {graphData.nodes[0] && (
          <button type="button" onClick={() => onNodeClick?.(graphData.nodes[0])}>
            Simulate node click
          </button>
        )}
        {graphData.links[0] && (
          <button type="button" onClick={() => onLinkClick?.(graphData.links[0])}>
            Simulate edge click
          </button>
        )}
        {graphData.nodes[0] && (
          <button type="button" onClick={paintFirstNode}>
            Simulate node paint
          </button>
        )}
      </div>
    );
  };

  return { default: ForceGraph2D };
});

vi.mock('../useGraphData', () => ({
  useGraphData: () => ({ data: mocks.graphData, loading: mocks.loading, reload: mocks.reload }),
}));

vi.mock('../useGraphLiveUpdates', () => ({
  useGraphLiveUpdates: () => ({ isConnected: mocks.isConnected }),
}));

vi.mock('../GraphViewLoader', () => ({ GraphViewLoader: () => null }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const nodes: GraphNode[] = [
  {
    id: 'node-a',
    label: 'First note',
    node_type: NodeType.NOTE,
    properties: {},
    position_x: null,
    position_y: null,
    user_id_hash: null,
  },
  {
    id: 'node-b',
    label: 'Related keyword',
    node_type: NodeType.KEYWORD,
    properties: {},
    position_x: null,
    position_y: null,
    user_id_hash: null,
  },
];

const edges: GraphEdge[] = [
  {
    id: 'edge-a-b',
    source: 'node-a',
    target: 'node-b',
    relationship_type: EdgeRelationshipType.RELATED_TO,
    weight: 0.75,
    properties: {},
  },
];

const graphData: GraphViewData = { nodes, edges };

beforeEach(() => {
  vi.clearAllMocks();
  mocks.graphData = null;
  mocks.loading = true;
  mocks.isConnected = false;
  mocks.context.fillStyle = '';
});

describe('GraphView component', () => {
  it('renders the nodes and passes their connecting edge to the graph canvas', () => {
    render(<GraphView data={graphData} />);

    expect(screen.getByRole('list', { name: 'Graph nodes' }).textContent).toContain('First note');
    expect(screen.getByRole('list', { name: 'Graph nodes' }).textContent).toContain('Related keyword');
    expect(screen.getByTestId('graph-links').textContent).toBe('edge-a-b:node-a->node-b');
  });

  it('sends the selected node to the callback and highlights it', () => {
    const onNodeClick = vi.fn();
    render(<GraphView data={graphData} onNodeClick={onNodeClick} />);

    fireEvent.click(screen.getByRole('button', { name: 'Simulate node click' }));

    expect(onNodeClick).toHaveBeenCalledWith(expect.objectContaining({
      id: 'node-a',
      label: 'First note',
      node_type: NodeType.NOTE,
    }));

    fireEvent.click(screen.getByRole('button', { name: 'Simulate node paint' }));
    expect(screen.getByTestId('painted-node-color').textContent).toBe(GRAPH_HIGHLIGHT_COLOR);
  });

  it('passes a normalized edge to the edge-click callback', () => {
    const onLinkClick: OnLinkClickCallback = vi.fn();
    const edgeWithoutProperties = { ...edges[0] };
    Reflect.deleteProperty(edgeWithoutProperties, 'properties');
    const dataWithApiEdge = {
      nodes,
      edges: [edgeWithoutProperties as unknown as GraphEdge],
    };
    render(<GraphView data={dataWithApiEdge} onLinkClick={onLinkClick} />);

    fireEvent.click(screen.getByRole('button', { name: 'Simulate edge click' }));

    expect(onLinkClick).toHaveBeenCalledWith({
      id: 'edge-a-b',
      source: 'node-a',
      target: 'node-b',
      relationship_type: EdgeRelationshipType.RELATED_TO,
      weight: 0.75,
      properties: {},
    });
  });

  it('renders an empty graph without nodes or links', () => {
    render(<GraphView data={{ nodes: [], edges: [] }} />);

    expect(screen.getByRole('list', { name: 'Graph nodes' }).children).toHaveLength(0);
    expect(screen.getByTestId('graph-links').textContent).toBe('');
  });
});

describe('GraphContainer loading state', () => {
  it('shows a loading message while graph data is being fetched', () => {
    mocks.loading = true;
    mocks.graphData = null;

    render(<GraphContainer />);

    expect(screen.getByText('Loading Graph...')).not.toBeNull();
  });

  it('offers a retry action when graph loading failed', () => {
    mocks.loading = false;
    mocks.graphData = null;

    render(<GraphContainer />);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(mocks.reload).toHaveBeenCalledOnce();
  });
});
