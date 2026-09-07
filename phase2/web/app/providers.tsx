"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { Role } from "@/lib/roles";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The corpus changes when an index build runs, not while someone reads a
      // page, so refetching on every window focus would be pure noise.
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

interface RoleContextValue {
  role: Role;
  setRole: (role: Role) => void;
}

const RoleContext = createContext<RoleContextValue | null>(null);

export function useRole(): RoleContextValue {
  const context = useContext(RoleContext);
  if (!context) throw new Error("useRole must be used within <Providers>");
  return context;
}

export function Providers({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<Role>("Leadership");
  const value = useMemo(() => ({ role, setRole }), [role]);
  return (
    <QueryClientProvider client={queryClient}>
      <RoleContext.Provider value={value}>{children}</RoleContext.Provider>
    </QueryClientProvider>
  );
}
