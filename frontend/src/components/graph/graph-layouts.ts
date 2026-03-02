import type { LayoutOptions } from 'cytoscape';

export type LayoutName = 'cose' | 'concentric' | 'grid';

export const LAYOUT_OPTIONS: Record<LayoutName, LayoutOptions> = {
  cose: {
    name: 'cose',
    animate: true,
    animationDuration: 800,
    nodeRepulsion: () => 8000,
    idealEdgeLength: () => 80,
    edgeElasticity: () => 100,
    gravity: 0.25,
    numIter: 1000,
    padding: 40,
  } as LayoutOptions,
  concentric: {
    name: 'concentric',
    animate: true,
    animationDuration: 600,
    padding: 40,
    minNodeSpacing: 50,
  } as LayoutOptions,
  grid: {
    name: 'grid',
    animate: true,
    animationDuration: 600,
    padding: 40,
    avoidOverlapPadding: 20,
  } as LayoutOptions,
};

export const LAYOUT_LABELS: Record<LayoutName, string> = {
  cose: 'Force-Directed (COSE)',
  concentric: 'Concentric',
  grid: 'Grid',
};
