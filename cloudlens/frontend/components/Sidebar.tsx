"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  MessageSquare,
  Server,
  ShieldAlert,
  ClipboardCheck,
  ScrollText,
  Settings,
  LogOut,
} from "lucide-react";
import { clearToken } from "@/lib/api";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/chat", label: "Agent console", icon: MessageSquare },
  { href: "/resources", label: "Resources", icon: Server },
  { href: "/security", label: "Security", icon: ShieldAlert },
  { href: "/approvals", label: "Approvals", icon: ClipboardCheck },
  { href: "/audit", label: "Audit log", icon: ScrollText },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <aside className="flex h-screen w-56 shrink-0 flex-col border-r border-white/8 bg-[#0a0b0f] px-3 py-4">
      <div className="mb-6 flex items-center gap-2 px-2">
        <div className="h-6 w-6 rounded-md bg-cyan-400" />
        <span className="text-sm font-semibold tracking-tight text-white/90">
          CloudLens
        </span>
      </div>

      <nav className="flex-1 space-y-0.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                active
                  ? "bg-cyan-400/10 text-cyan-300"
                  : "text-white/50 hover:bg-white/5 hover:text-white/85"
              }`}
            >
              <Icon size={16} strokeWidth={2} />
              {label}
            </Link>
          );
        })}
      </nav>

      <button
        onClick={() => {
          clearToken();
          router.push("/login");
        }}
        className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-white/40 transition-colors hover:bg-white/5 hover:text-white/80"
      >
        <LogOut size={16} strokeWidth={2} />
        Sign out
      </button>
    </aside>
  );
}
