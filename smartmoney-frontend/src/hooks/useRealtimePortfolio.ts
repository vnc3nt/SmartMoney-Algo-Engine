"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import type { PerformanceSnapshot, OpenPosition } from "@/types/trading";
import type { RealtimeChannel } from "@supabase/supabase-js";

export function useRealtimeSnapshots(strategyId: string) {
  const [snapshots, setSnapshots] = useState<PerformanceSnapshot[]>([]);

  useEffect(() => {
    const supabase = createClient();
    // 1. Initial data load
    const fetchInitial = async () => {
      const { data } = await supabase
        .schema("trades")
        .from("performance_snapshots")
        .select("*")
        .eq("strategy_id", strategyId)
        .order("snapshot_date", { ascending: true })
        .limit(90);

      if (data) setSnapshots(data);
    };

    fetchInitial();

    // 2. Realtime channel for new snapshots
    const channel: RealtimeChannel = supabase
      .channel(`snapshots:${strategyId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "trades",
          table: "performance_snapshots",
          filter: `strategy_id=eq.${strategyId}`,
        },
        (payload) => {
          setSnapshots((prev) => [...prev, payload.new as PerformanceSnapshot]);
        }
      )
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "trades",
          table: "performance_snapshots",
          filter: `strategy_id=eq.${strategyId}`,
        },
        (payload) => {
          setSnapshots((prev) =>
            prev.map((s) =>
              s.snapshot_date === (payload.new as PerformanceSnapshot).snapshot_date
                ? (payload.new as PerformanceSnapshot)
                : s
            )
          );
        }
      )
      .subscribe();

    // 3. Cleanup on unmount
    return () => {
      supabase.removeChannel(channel);
    };
  }, [strategyId]);

  return snapshots;
}

export function useRealtimePositions(portfolioId: string) {
  const [positions, setPositions] = useState<OpenPosition[]>([]);

  useEffect(() => {
    const supabase = createClient();
    const fetchInitial = async () => {
      const { data } = await supabase
        .schema("trades")
        .from("open_positions")
        .select("*")
        .eq("portfolio_id", portfolioId);

      if (data) setPositions(data);
    };

    fetchInitial();

    const channel: RealtimeChannel = supabase
      .channel(`positions:${portfolioId}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "trades",
          table: "open_positions",
          filter: `portfolio_id=eq.${portfolioId}`,
        },
        (payload) => {
          if (payload.eventType === "INSERT") {
            setPositions((prev) => [...prev, payload.new as OpenPosition]);
          } else if (payload.eventType === "UPDATE") {
            setPositions((prev) =>
              prev.map((p) =>
                p.id === payload.new.id ? (payload.new as OpenPosition) : p
              )
            );
          } else if (payload.eventType === "DELETE") {
            setPositions((prev) =>
              prev.filter((p) => p.id !== payload.old.id)
            );
          }
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [portfolioId]);

  return positions;
}
