"use client";

import { useEffect, useState } from "react";
import {
  CatalogImportResponse,
  CatalogStatusResponse,
  MenuPdfStatusResponse,
  deleteMenuPdf,
  getCatalogStatus,
  getMenuPdfStatus,
  getPublicMenuUrl,
  importConsumerCatalog,
  uploadMenuPdf,
} from "@/lib/catalog-api";

function formatDate(value?: string | null) {
  if (!value) return "—";

  return new Date(value).toLocaleString("pt-BR");
}

export function CatalogPanel({
  storeId,
}: {
  storeId: string;
}) {
  const [data, setData] = useState<CatalogStatusResponse | null>(null);
  const [menuPdf, setMenuPdf] =
    useState<MenuPdfStatusResponse | null>(null);

  const [mainFile, setMainFile] = useState<File | null>(null);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfInputKey, setPdfInputKey] = useState(0);
  const [complementsFile, setComplementsFile] =
    useState<File | null>(null);
  const [prodconFile, setProdconFile] = useState<File | null>(null);

  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);

  const [message, setMessage] = useState("");
  const [lastImport, setLastImport] =
    useState<CatalogImportResponse | null>(null);

  async function load() {
    setLoading(true);

    try {
      const [result, pdfStatus] = await Promise.all([
        getCatalogStatus(storeId),
        getMenuPdfStatus(storeId),
      ]);

      setData(result);
      setMenuPdf(pdfStatus);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Erro ao carregar o cardápio.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId]);

  async function importCatalog() {
    if (!mainFile) {
      setMessage("Selecione o Excel principal.");
      return;
    }

    if (!prodconFile) {
      setMessage("Selecione o arquivo .prodcon do Consumer.");
      return;
    }

    const confirmed = window.confirm(
      "Importar estes arquivos como uma nova versão do cardápio?\n\n" +
        "A versão atual continuará registrada no histórico.",
    );

    if (!confirmed) {
      return;
    }

    setImporting(true);
    setMessage("");
    setLastImport(null);

    try {
      const result = await importConsumerCatalog(
        storeId,
        {
          mainFile,
          complementsFile,
          prodconFile,
        },
      );

      setLastImport(result);

      setMessage(
        `Cardápio ${result.version_code} importado e ativado com sucesso.`,
      );

      setMainFile(null);
      setComplementsFile(null);
      setProdconFile(null);

      await load();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Erro ao importar cardápio.",
      );
    } finally {
      setImporting(false);
    }
  }

  async function savePdf() {
    if (!pdfFile) {
      setMessage("Selecione o arquivo PDF do cardápio.");
      return;
    }

    setPdfBusy(true);
    setMessage("");

    try {
      const result = await uploadMenuPdf(
        storeId,
        pdfFile,
      );

      setMenuPdf(result);
      setPdfFile(null);
      setPdfInputKey((value) => value + 1);

      setMessage(
        `PDF vinculado à versão ${
          result.active_version_code ?? "ativa"
        } com sucesso.`,
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Erro ao enviar PDF.",
      );
    } finally {
      setPdfBusy(false);
    }
  }

  async function removePdf() {
    const confirmed = window.confirm(
      "Remover o cardápio PDF desta loja?",
    );

    if (!confirmed) {
      return;
    }

    setPdfBusy(true);
    setMessage("");

    try {
      await deleteMenuPdf(storeId);

      const status = await getMenuPdfStatus(storeId);

      setMenuPdf(status);
      setPdfFile(null);
      setMessage("Cardápio PDF removido.");
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Erro ao remover PDF.",
      );
    } finally {
      setPdfBusy(false);
    }
  }

  if (loading) {
    return (
      <section
        className="panel wide"
        id="cardapios"
        style={{ gridColumn: "1 / -1" }}
      >
        Carregando cardápio...
      </section>
    );
  }

  const active = data?.active_version ?? null;

  return (
    <section
      className="panel wide"
      id="cardapios"
      style={{
        gridColumn: "1 / -1",
        marginTop: 24,
      }}
    >
      <header className="panelHeader">
        <div>
          <p className="eyebrow">CATÁLOGO OPERACIONAL</p>
          <h2>Cardápios</h2>
          <p>
            Produtos, famílias, complementos e códigos PDV usados pela Olívia.
          </p>
        </div>

        {active && (
          <div
            style={{
              padding: "9px 14px",
              borderRadius: 999,
              fontWeight: 800,
              background: "#e9f6ed",
              color: "#22633b",
            }}
          >
            ● {active.version_code}
          </div>
        )}
      </header>

      {active ? (
        <>
          <div
            style={{
              padding: 16,
              background: "#f8f8f6",
              borderRadius: 12,
              marginBottom: 20,
            }}
          >
            <strong>Versão ativa</strong>

            <div
              className="miniGrid"
              style={{ marginTop: 14 }}
            >
              <div className="miniValue">
                <strong>{active.products_count}</strong>
                <span>Produtos disponíveis</span>
              </div>

              <div className="miniValue">
                <strong>{active.modifiers_count}</strong>
                <span>Complementos</span>
              </div>

              <div className="miniValue">
                <strong>{active.relations_count}</strong>
                <span>Vínculos produto ↔ complemento</span>
              </div>

              <div className="miniValue">
                <strong>{active.provider}</strong>
                <span>Integração</span>
              </div>
            </div>

            <p
              className="muted"
              style={{ marginTop: 14 }}
            >
              Ativado em {formatDate(active.activated_at)}
            </p>
          </div>

          <h3>Arquivos da versão ativa</h3>

          <div style={{ marginTop: 10 }}>
            {active.source_files?.length ? (
              active.source_files.map((file) => (
                <div
                  className="statusRow"
                  key={`${file.role}-${file.original_name}`}
                >
                  <div>
                    <strong>{file.original_name}</strong>
                    <div
                      className="muted"
                      style={{
                        fontSize: 13,
                        marginTop: 3,
                      }}
                    >
                      {file.role} · {file.format}
                    </div>
                  </div>

                  <span>
                    {file.role === "MAIN"
                      ? "Excel principal"
                      : file.role === "COMPLEMENTS"
                        ? "Excel de complementos"
                        : file.role === "PRODCON"
                          ? "Relações Consumer"
                          : file.role}
                  </span>
                </div>
              ))
            ) : (
              <p className="muted">
                Esta versão não possui arquivos-fonte registrados.
              </p>
            )}
          </div>
        </>
      ) : (
        <div
          style={{
            padding: 16,
            background: "#fff8e7",
            borderRadius: 12,
            marginBottom: 20,
          }}
        >
          <strong>Nenhuma versão ativa encontrada.</strong>
        </div>
      )}

      <div
        style={{
          marginTop: 28,
          paddingTop: 24,
          borderTop: "1px solid #e4e7e1",
        }}
      >
        <h3>Importar nova versão</h3>

        <p
          className="muted"
          style={{ marginTop: 6 }}
        >
          Para Consumer, o Excel principal e o arquivo .prodcon são
          obrigatórios. O Excel de complementos é opcional e será armazenado
          junto da mesma versão.
        </p>

        <div
          style={{
            display: "grid",
            gridTemplateColumns:
              "repeat(auto-fit, minmax(240px, 1fr))",
            gap: 14,
            marginTop: 18,
          }}
        >
          <label
            style={{
              padding: 16,
              border: "1px solid #dde2dc",
              borderRadius: 12,
            }}
          >
            <strong>1. Excel principal *</strong>

            <p
              className="muted"
              style={{
                fontSize: 13,
                margin: "5px 0 12px",
              }}
            >
              Produtos, preços, categorias e Código PDV.
            </p>

            <input
              type="file"
              accept=".xlsx"
              disabled={importing}
              onChange={(event) =>
                setMainFile(
                  event.target.files?.[0] ?? null,
                )
              }
            />

            {mainFile && (
              <p style={{ marginTop: 8 }}>
                ✓ {mainFile.name}
              </p>
            )}
          </label>

          <label
            style={{
              padding: 16,
              border: "1px solid #dde2dc",
              borderRadius: 12,
            }}
          >
            <strong>2. Excel de complementos</strong>

            <p
              className="muted"
              style={{
                fontSize: 13,
                margin: "5px 0 12px",
              }}
            >
              Opcional. Ficará registrado na versão do catálogo.
            </p>

            <input
              type="file"
              accept=".xlsx"
              disabled={importing}
              onChange={(event) =>
                setComplementsFile(
                  event.target.files?.[0] ?? null,
                )
              }
            />

            {complementsFile && (
              <p style={{ marginTop: 8 }}>
                ✓ {complementsFile.name}
              </p>
            )}
          </label>

          <label
            style={{
              padding: 16,
              border: "1px solid #dde2dc",
              borderRadius: 12,
            }}
          >
            <strong>3. Arquivo .prodcon *</strong>

            <p
              className="muted"
              style={{
                fontSize: 13,
                margin: "5px 0 12px",
              }}
            >
              Complementos, vínculos e disponibilidade do Consumer.
            </p>

            <input
              type="file"
              accept=".prodcon"
              disabled={importing}
              onChange={(event) =>
                setProdconFile(
                  event.target.files?.[0] ?? null,
                )
              }
            />

            {prodconFile && (
              <p style={{ marginTop: 8 }}>
                ✓ {prodconFile.name}
              </p>
            )}
          </label>
        </div>

        <div
          style={{
            display: "flex",
            gap: 14,
            alignItems: "center",
            marginTop: 20,
            flexWrap: "wrap",
          }}
        >
          <button
            type="button"
            className="refreshButton"
            disabled={
              importing ||
              !mainFile ||
              !prodconFile
            }
            onClick={() => void importCatalog()}
            style={{
              background: "#244c36",
              color: "white",
            }}
          >
            {importing
              ? "Importando..."
              : "Importar nova versão"}
          </button>

          <button
            type="button"
            className="refreshButton"
            disabled={importing}
            onClick={() => void load()}
          >
            Atualizar status
          </button>
        </div>

        {message && (
          <div
            style={{
              marginTop: 16,
              padding: 12,
              borderRadius: 10,
              background: "#f8f8f6",
            }}
          >
            {message}
          </div>
        )}

        {lastImport && (
          <div
            style={{
              marginTop: 18,
              padding: 16,
              borderRadius: 12,
              background: "#e9f6ed",
            }}
          >
            <strong>
              ✓ {lastImport.version_code} ativado
            </strong>

            <div
              className="miniGrid"
              style={{ marginTop: 12 }}
            >
              <div className="miniValue">
                <strong>{lastImport.products_count}</strong>
                <span>Produtos disponíveis</span>
              </div>

              <div className="miniValue">
                <strong>{lastImport.family_import.families_found}</strong>
                <span>Famílias</span>
              </div>

              <div className="miniValue">
                <strong>{lastImport.modifiers_count}</strong>
                <span>Complementos</span>
              </div>

              <div className="miniValue">
                <strong>{lastImport.relations_count}</strong>
                <span>Vínculos</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {data?.versions?.length ? (
        <div
          style={{
            marginTop: 30,
            paddingTop: 24,
            borderTop: "1px solid #e4e7e1",
          }}
        >
          <h3>Histórico de versões</h3>

          <div style={{ marginTop: 10 }}>
            {data.versions.map((version) => (
              <div
                className="statusRow"
                key={version.id}
              >
                <div>
                  <strong>
                    {version.version_code}
                  </strong>

                  <div
                    className="muted"
                    style={{
                      fontSize: 13,
                      marginTop: 3,
                    }}
                  >
                    {formatDate(version.created_at)}
                  </div>
                </div>

                <strong>
                  {version.active
                    ? "ATIVO"
                    : version.status}
                </strong>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div
        style={{
          marginTop: 28,
          padding: 18,
          border: "1px solid #dfe4de",
          borderRadius: 12,
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 16,
            alignItems: "flex-start",
            flexWrap: "wrap",
          }}
        >
          <div>
            <strong>Cardápio visual em PDF</strong>

            <p
              className="muted"
              style={{ marginTop: 5 }}
            >
              Arquivo que poderá ser enviado ao cliente pelo WhatsApp.
            </p>
          </div>

          {menuPdf?.exists && (
            <div
              style={{
                padding: "8px 12px",
                borderRadius: 999,
                fontWeight: 800,
                background: menuPdf.synchronized
                  ? "#e9f6ed"
                  : "#fff3d6",
                color: menuPdf.synchronized
                  ? "#22633b"
                  : "#8a5a00",
              }}
            >
              {menuPdf.synchronized
                ? `● SINCRONIZADO COM ${
                    menuPdf.active_version_code ?? "CATÁLOGO"
                  }`
                : "● PDF DESATUALIZADO"}
            </div>
          )}
        </div>

        {menuPdf?.document ? (
          <div
            style={{
              marginTop: 16,
              padding: 16,
              background: "#f8f8f6",
              borderRadius: 12,
            }}
          >
            <strong>{menuPdf.document.original_name}</strong>

            <p
              className="muted"
              style={{ marginTop: 5 }}
            >
              Vinculado a{" "}
              {menuPdf.document.catalog_version_code ?? "versão desconhecida"}
              {" · "}
              Atualizado em {formatDate(menuPdf.document.updated_at)}
            </p>

            {!menuPdf.synchronized && (
              <p
                style={{
                  marginTop: 10,
                  fontWeight: 700,
                  color: "#8a5a00",
                }}
              >
                O catálogo operacional mudou depois deste PDF.
                Envie uma versão visual atualizada antes de oferecê-lo
                aos clientes.
              </p>
            )}

            <div
              style={{
                display: "flex",
                gap: 10,
                marginTop: 14,
                flexWrap: "wrap",
              }}
            >
              <a
                className="refreshButton"
                href={getPublicMenuUrl(
                  menuPdf.document.public_path,
                )}
                target="_blank"
                rel="noreferrer"
                style={{
                  textDecoration: "none",
                }}
              >
                Abrir PDF
              </a>

              <button
                type="button"
                className="refreshButton"
                disabled={pdfBusy}
                onClick={() => void removePdf()}
              >
                Remover PDF
              </button>
            </div>
          </div>
        ) : (
          <div
            style={{
              marginTop: 16,
              padding: 14,
              background: "#fff8e7",
              borderRadius: 10,
            }}
          >
            Nenhum PDF cadastrado.
          </div>
        )}

        <div
          style={{
            marginTop: 18,
            paddingTop: 18,
            borderTop: "1px solid #e4e7e1",
          }}
        >
          <strong>
            {menuPdf?.exists
              ? "Substituir PDF"
              : "Enviar PDF"}
          </strong>

          <div
            style={{
              display: "flex",
              gap: 12,
              alignItems: "center",
              flexWrap: "wrap",
              marginTop: 12,
            }}
          >
            <input
              key={pdfInputKey}
              type="file"
              accept=".pdf,application/pdf"
              disabled={pdfBusy}
              onChange={(event) =>
                setPdfFile(
                  event.target.files?.[0] ?? null,
                )
              }
            />

            <button
              type="button"
              className="refreshButton"
              disabled={pdfBusy || !pdfFile}
              onClick={() => void savePdf()}
              style={{
                background: "#244c36",
                color: "white",
              }}
            >
              {pdfBusy
                ? "Enviando..."
                : menuPdf?.exists
                  ? "Atualizar PDF"
                  : "Enviar PDF"}
            </button>
          </div>

          {pdfFile && (
            <p
              className="muted"
              style={{ marginTop: 8 }}
            >
              ✓ {pdfFile.name}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
