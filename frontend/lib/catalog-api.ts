export type CatalogSourceFile = {
  role: "MAIN" | "COMPLEMENTS" | "PRODCON" | string;
  format: "XLSX" | "PRODCON" | string;
  original_name: string;
  sha256: string;
  updated_at: string;
};

export type CatalogVersion = {
  id: string;
  version_code: string;
  provider: string;
  status: string;
  active?: boolean;
  products_count: number;
  modifiers_count: number;
  relations_count: number;
  created_at?: string;
  activated_at: string | null;
  notes?: string | null;
  source_files?: CatalogSourceFile[];
};

export type CatalogStatusResponse = {
  store_id: string;
  store_name: string;
  active_version: CatalogVersion | null;
  versions: CatalogVersion[];
};

export type CatalogImportResponse = {
  ok: boolean;
  store_id: string;
  version_code: string;
  status: string;
  products_count: number;
  modifiers_count: number;
  relations_count: number;

  main_import: {
    rows_read: number;
    rows_valid: number;
    products_created: number;
    products_updated: number;
    products_deactivated: number;
    invalid_rows: number;
    conflicts_skipped: number;
  };

  complements_excel: {
    provided: boolean;
    stored: boolean;
    imported: boolean;
    note: string;
  };

  family_import: {
    families_found: number;
    families_created: number;
    families_updated: number;
    families_deactivated: number;
    product_links: number;
    child_products_missing: number;
  };

  prodcon_import: {
    consumer_version: string | null;
    modifiers_created: number;
    modifiers_updated: number;
    products_with_complements: number;
    relations_created: number;
    products_not_found: number;
  };
};

const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

async function apiError(response: Response): Promise<never> {
  let message = `Erro HTTP ${response.status}`;

  try {
    const body = await response.json();

    if (typeof body?.detail === "string") {
      message = body.detail;
    }
  } catch {
    const text = await response.text();

    if (text) {
      message = text;
    }
  }

  throw new Error(message);
}

export async function getCatalogStatus(
  storeId: string,
): Promise<CatalogStatusResponse> {
  const response = await fetch(
    `${API}/api/v1/operations/stores/${storeId}/catalog`,
    {
      cache: "no-store",
    },
  );

  if (!response.ok) {
    return apiError(response);
  }

  return response.json();
}

export async function importConsumerCatalog(
  storeId: string,
  files: {
    mainFile: File;
    complementsFile?: File | null;
    prodconFile: File;
  },
): Promise<CatalogImportResponse> {
  const form = new FormData();

  form.append("main_file", files.mainFile);

  if (files.complementsFile) {
    form.append("complements_file", files.complementsFile);
  }

  form.append("prodcon_file", files.prodconFile);

  const response = await fetch(
    `${API}/api/v1/operations/stores/${storeId}/catalog/import/consumer`,
    {
      method: "POST",
      body: form,
    },
  );

  if (!response.ok) {
    return apiError(response);
  }

  return response.json();
}
