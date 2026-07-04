// Drives the asynchronous-solve UX: kick off a solve, then poll the job until
// it finishes, exposing status + result so the UI can show progress and surface
// the outcome. Mirrors the backend's POST /solve -> poll /jobs/{id} contract.
import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { SolveJob, SolveRequest } from "@/api/types";
import { qk } from "./queries";

type Phase = "idle" | "queued" | "running" | "succeeded" | "failed";

export function useSolve() {
  const qc = useQueryClient();
  const [phase, setPhase] = useState<Phase>("idle");
  const [job, setJob] = useState<SolveJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const clock = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    if (clock.current) clearInterval(clock.current);
    timer.current = null;
    clock.current = null;
  }, []);

  useEffect(() => () => stop(), [stop]);

  const start = useCallback(
    async (req: SolveRequest) => {
      setError(null);
      setJob(null);
      setElapsed(0);
      setPhase("queued");
      clock.current = setInterval(() => setElapsed((e) => e + 1), 1000);
      try {
        const kicked = await api.solve(req);
        setJob(kicked);
        // poll
        timer.current = setInterval(async () => {
          try {
            const j = await api.getJob(kicked.job_id);
            setJob(j);
            if (j.status === "running") setPhase("running");
            if (j.status === "succeeded" || j.status === "failed") {
              setPhase(j.status);
              stop();
              if (j.status === "succeeded") {
                // refresh any schedule-dependent views
                qc.invalidateQueries({ queryKey: qk.watchlist });
                qc.invalidateQueries({ queryKey: qk.summary });
              } else {
                setError(j.error ?? "Solve failed.");
              }
            }
          } catch (e) {
            stop();
            setPhase("failed");
            setError(e instanceof Error ? e.message : "Lost contact while solving.");
          }
        }, 1000);
      } catch (e) {
        stop();
        setPhase("failed");
        setError(e instanceof Error ? e.message : "Couldn't start the solve.");
      }
    },
    [qc, stop],
  );

  const reset = useCallback(() => {
    stop();
    setPhase("idle");
    setJob(null);
    setError(null);
    setElapsed(0);
  }, [stop]);

  const busy = phase === "queued" || phase === "running";
  return { phase, job, error, elapsed, busy, start, reset };
}