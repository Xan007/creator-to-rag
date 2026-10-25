import { useState, useEffect, useCallback } from "react";

interface UseSidebarResizeOptions {
  defaultWidth?: number;
  minWidth?: number;
  maxWidth?: number;
}

export function useSidebarResize({
  defaultWidth = 256,
  minWidth = 180,
  maxWidth = 480,
}: UseSidebarResizeOptions = {}) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(() => window.matchMedia('(min-width: 768px)').matches);
  const [sidebarWidth, setSidebarWidth] = useState(defaultWidth);
  const [isDragging, setIsDragging] = useState(false);

  const startDragging = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const resizeBy = useCallback(
    (delta: number) => {
      setSidebarWidth((previous) =>
        Math.max(minWidth, Math.min(maxWidth, previous + delta)),
      );
    },
    [minWidth, maxWidth],
  );

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const newWidth = Math.max(minWidth, Math.min(maxWidth, e.clientX));
      setSidebarWidth(newWidth);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging, minWidth, maxWidth]);

  return {
    isSidebarOpen,
    setIsSidebarOpen,
    sidebarWidth,
    isDragging,
    startDragging,
    resizeBy,
  };
}
