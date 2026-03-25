import { useState, useEffect } from "react";
import { fetchPngBlobUrl, pngDownloadUrl, excalidrawDownloadUrl, downloadFile } from "../api";

export default function DiagramViewer({ excalidrawFile, runId }) {
  const [pngBlobUrl, setPngBlobUrl] = useState(null);
  const [showInteractive, setShowInteractive] = useState(false);
  const [ExcalidrawComp, setExcalidrawComp] = useState(null);
  const [excalidrawAPI, setExcalidrawAPI] = useState(null);

  useEffect(() => {
    if (runId) {
      fetchPngBlobUrl(runId).then(setPngBlobUrl);
    }
  }, [runId]);

  // Scroll all elements into view once the API is ready
  useEffect(() => {
    if (!excalidrawAPI) return;
    const timer = setTimeout(() => {
      excalidrawAPI.scrollToContent(undefined, { fitToContent: true, viewportZoomFactor: 0.85 });
    }, 150);
    return () => clearTimeout(timer);
  }, [excalidrawAPI]);

  useEffect(() => {
    console.log("excalidrawFile:", excalidrawFile);
    console.log("elements count:", excalidrawFile?.elements?.length);
    console.log("files keys:", excalidrawFile?.files ? Object.keys(excalidrawFile.files) : "none");
  }, [excalidrawFile]);

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
            excalidrawAPI={(api) => setExcalidrawAPI(api)}
            initialData={{
              elements: excalidrawFile.elements || [],
              files: excalidrawFile.files || {},
              appState: { viewBackgroundColor: "#ffffff" },
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
