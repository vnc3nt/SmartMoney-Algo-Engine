"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import type { Strategy, Portfolio } from "@/types/trading";

export function useStrategies() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const supabase = createClient();

    const fetchData = async () => {
      try {
        // Fetch active strategies from trades schema
        const { data: strategiesData, error: strategiesError } = await supabase
          .schema("trades")
          .from("strategies")
          .select("*")
          .eq("is_active", true);

        if (strategiesError) {
          console.error("Strategies error:", strategiesError);
        }

        if (strategiesData) {
          setStrategies(strategiesData);
          // Set first strategy as default
          if (strategiesData.length > 0) {
            setSelectedStrategyId(strategiesData[0].id);
          }
        }

        // Fetch all portfolios from trades schema
        const { data: portfoliosData, error: portfoliosError } = await supabase
          .schema("trades")
          .from("portfolios")
          .select("*");

        if (portfoliosError) {
          console.error("Portfolios error:", portfoliosError);
        }

        if (portfoliosData) {
          setPortfolios(portfoliosData);
        }
      } catch (error) {
        console.error("Failed to fetch strategies:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const selectedStrategy = strategies.find((s) => s.id === selectedStrategyId);
  const selectedPortfolio = portfolios.find((p) => p.strategy_id === selectedStrategyId);

  return {
    strategies,
    portfolios,
    selectedStrategyId,
    selectedStrategy,
    selectedPortfolio,
    setSelectedStrategyId,
    loading,
  };
}

