// React Query hooks wrapping the API client. Centralises caching, loading,
// and error state so screens stay declarative.
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type {
  OrderCreate, EventCreate, BomCreate, BomUpdate,
  RoutingCreate, RoutingOpCreate, RoutingOpUpdate,
} from "@/api/types";

export const qk = {
  summary: ["summary"] as const,
  watchlist: ["watchlist"] as const,
  products: ["products"] as const,
  orders: ["orders"] as const,
  routings: ["routings"] as const,
  bom: (pid?: number) => ["bom", pid] as const,
  events: (oid?: number) => ["events", oid] as const,
  orderSchedule: (oid: string) => ["orderSchedule", oid] as const,
  gantt: ["gantt"] as const,
  openAlerts: ["alerts", "open"] as const,
};

export const useSummary = () => useQuery({ queryKey: qk.summary, queryFn: api.summary });
export const useWatchlist = () => useQuery({ queryKey: qk.watchlist, queryFn: api.watchlist });
export const useProducts = () => useQuery({ queryKey: qk.products, queryFn: api.listProducts });
export const useOrders = () => useQuery({ queryKey: qk.orders, queryFn: api.listOrders });
export const useRoutings = () => useQuery({ queryKey: qk.routings, queryFn: api.listRoutings });
export const useBom = (pid?: number) =>
  useQuery({ queryKey: qk.bom(pid), queryFn: () => api.listBom(pid), enabled: pid != null });
export const useEvents = (oid?: number) =>
  useQuery({ queryKey: qk.events(oid), queryFn: () => api.listEvents(oid) });
export const useOrderSchedule = (oid: string) =>
  useQuery({ queryKey: qk.orderSchedule(oid), queryFn: () => api.getOrderSchedule(oid), enabled: !!oid });

export function useCreateOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (o: OrderCreate) => api.createOrder(o),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.orders });
      qc.invalidateQueries({ queryKey: qk.summary });
      qc.invalidateQueries({ queryKey: qk.watchlist });
    },
  });
}

export function useCreateEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (e: EventCreate) => api.createEvent(e),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: qk.events(vars.order_id) });
      qc.invalidateQueries({ queryKey: qk.events(undefined) });
    },
  });
}

export function useCreateBom(productId?: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: BomCreate) => api.createBom(b),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.bom(productId) }),
  });
}

export function useUpdateBom(productId?: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ pk, patch }: { pk: number; patch: BomUpdate }) => api.updateBom(pk, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.bom(productId) }),
  });
}

export function useDeleteBom(productId?: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (pk: number) => api.deleteBom(pk),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.bom(productId) }),
  });
}

function useRoutingInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: qk.routings });
}

export function useCreateRouting() {
  const invalidate = useRoutingInvalidate();
  return useMutation({ mutationFn: (r: RoutingCreate) => api.createRouting(r), onSuccess: invalidate });
}

export function useDeleteRouting() {
  const invalidate = useRoutingInvalidate();
  return useMutation({ mutationFn: (pk: number) => api.deleteRouting(pk), onSuccess: invalidate });
}

export function useAddOperation() {
  const invalidate = useRoutingInvalidate();
  return useMutation({
    mutationFn: ({ routingPk, op }: { routingPk: number; op: RoutingOpCreate }) =>
      api.addOperation(routingPk, op),
    onSuccess: invalidate,
  });
}

export function useUpdateOperation() {
  const invalidate = useRoutingInvalidate();
  return useMutation({
    mutationFn: ({ routingPk, opPk, patch }: { routingPk: number; opPk: number; patch: RoutingOpUpdate }) =>
      api.updateOperation(routingPk, opPk, patch),
    onSuccess: invalidate,
  });
}

export function useDeleteOperation() {
  const invalidate = useRoutingInvalidate();
  return useMutation({
    mutationFn: ({ routingPk, opPk }: { routingPk: number; opPk: number }) =>
      api.deleteOperation(routingPk, opPk),
    onSuccess: invalidate,
  });
}
