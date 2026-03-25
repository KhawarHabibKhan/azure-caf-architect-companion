import { useState, useEffect } from "react";
import { fetchPngBlobUrl, pngDownloadUrl, excalidrawDownloadUrl, downloadFile } from "../api";

export default function DiagramViewer({ excalidrawFile, runId }) {
  const [pngBlobUrl, setPngBlobUrl] = useState(null);
  const [showInteractive, setShowInteractive] = useState(false);
  const [ExcalidrawComp, setExcalidrawComp] = useState(null);

  useEffect(() => {
    if (runId) {
      fetchPngBlobUrl(runId).then(setPngBlobUrl);
    }
  }, [runId]);

  const loadExcalidraw = async () => {
    if (!ExcalidrawComp) {
      const mod = await import("@excalidraw/excalidraw");
      await import("@excalidraw/excalidraw/index.css");
      setExcalidrawComp(() => mod.Excalidraw);
    }
    setShowInteractive(true);
  };

  return (
    <div className="card">
      <h3>Landing Zone Architecture</h3>
      <div className="btn-row" style={{ marginBottom: 12 }}>
        {runId && (
          <>
            <button className="btn btn-secondary" onClick={() => downloadFile(pngDownloadUrl(runId), `caf_architecture_${runId}.png`)}>
              Download PNG
            </button>
            <button className="btn btn-secondary" onClick={() => downloadFile(excalidrawDownloadUrl(runId), `caf_architecture_${runId}.excalidraw`)}>
              Download Excalidraw
            </button>
          </>
        )}
        {excalidrawFile && (
          <button className="btn btn-secondary" onClick={() => showInteractive ? setShowInteractive(false) : loadExcalidraw()}>
            {showInteractive ? "Show PNG" : "Interactive View"}
          </button>
        )}
      </div>

      <div className="diagram-container">
        {showInteractive && ExcalidrawComp && excalidrawFile ? (
          <ExcalidrawComp
            initialData={{
              elements: excalidrawFile.elements || [],
              files: excalidrawFile.files || {},
              appState: { viewBackgroundColor: "#ffffff", zoom: { value: 0.85 } },
              scrollToContent: true,
            }}
          />
        ) : pngBlobUrl ? (
          <img src={pngBlobUrl} alt="Landing zone architecture diagram" />
        ) : (
          <p style={{ padding: 20, color: "#999" }}>No diagram available</p>
        )}
      </div>
    </div>
  );
}
