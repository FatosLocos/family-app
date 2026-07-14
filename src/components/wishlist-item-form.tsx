"use client";

import { Gift, Loader2, Plus, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import type { AppData } from "@/lib/types";

type WishlistAction = (formData: FormData) => void | Promise<void>;
type PreviewState = "idle" | "loading" | "success" | "error";

type PreviewResponse = {
  title?: string | null;
  image_url?: string | null;
  category?: string | null;
  price?: string | null;
  error?: string;
};

export function WishlistItemSmartForm({ action, members = [] }: { action: WishlistAction; members?: AppData["members"] }) {
  const [isOpen, setIsOpen] = useState(false);
  const [isClosing, setIsClosing] = useState(false);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("Cadeau");
  const [price, setPrice] = useState("");
  const [url, setUrl] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [previewState, setPreviewState] = useState<PreviewState>("idle");
  const [previewMessage, setPreviewMessage] = useState("Plak een link om titel, categorie, afbeelding en richtprijs op te halen.");
  const lastPreviewUrl = useRef("");
  const closeTimer = useRef<number | null>(null);

  useEffect(() => () => {
    if (closeTimer.current) window.clearTimeout(closeTimer.current);
  }, []);

  const memberOptions = useMemo(
    () =>
      members.map((member) => ({
        id: member.user_id,
        name: member.profile?.full_name ?? member.profile?.email ?? "Gezinslid",
      })),
    [members],
  );

  useEffect(() => {
    if (!url.trim()) {
      lastPreviewUrl.current = "";
      setPreviewState("idle");
      setPreviewMessage("Plak een link om titel, categorie, afbeelding en richtprijs op te halen.");
      return;
    }
    const previewUrl = url.trim();
    if (lastPreviewUrl.current === previewUrl) return;

    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      lastPreviewUrl.current = previewUrl;
      setPreviewState("loading");
      setPreviewMessage("Link wordt gelezen...");
      try {
        const response = await fetch("/api/wishlist/preview", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ url: previewUrl }),
          signal: controller.signal,
        });
        const preview = (await response.json()) as PreviewResponse;
        if (!response.ok) throw new Error(preview.error || "Preview mislukt.");

        if (!title && preview.title) setTitle(preview.title);
        if ((!category || category === "Cadeau") && preview.category) setCategory(preview.category);
        if (!price && preview.price) setPrice(preview.price);
        if (!imageUrl && preview.image_url) setImageUrl(preview.image_url);

        const found = [preview.title, preview.category, preview.price, preview.image_url].filter(Boolean).length;
        setPreviewState(found > 0 ? "success" : "idle");
        setPreviewMessage(found > 0 ? "Gegevens aangevuld vanuit de link. Controleer ze voor opslaan." : "Geen productgegevens gevonden; je kunt de velden handmatig invullen.");
      } catch (error) {
        if (controller.signal.aborted) return;
        setPreviewState("error");
        setPreviewMessage(error instanceof Error ? error.message : "Preview ophalen is niet gelukt.");
      }
    }, 650);

    return () => {
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [category, imageUrl, price, title, url]);

  function onUrlChange(event: ChangeEvent<HTMLInputElement>) {
    setUrl(event.target.value);
  }

  function openOverlay() {
    if (closeTimer.current) window.clearTimeout(closeTimer.current);
    setIsClosing(false);
    setIsOpen(true);
  }

  function closeOverlay() {
    if (isClosing) return;
    setIsClosing(true);
    closeTimer.current = window.setTimeout(() => {
      setIsOpen(false);
      setIsClosing(false);
    }, 180);
  }

  if (!isOpen) {
    return (
      <section className="card wishlist-add-collapsed">
        <button className="wishlist-add-trigger" type="button" onClick={openOverlay} aria-expanded="false" aria-haspopup="dialog">
          <span className="summary-icon">
            <Plus size={18} />
          </span>
          <span>
            <strong>Wens toevoegen</strong>
            <small>Link plakken, automatisch aanvullen en opslaan</small>
          </span>
        </button>
      </section>
    );
  }

  return (
    <div className={`app-overlay-shell wishlist-overlay-shell${isClosing ? " is-closing" : ""}`} role="dialog" aria-modal="true" aria-labelledby="wishlist-add-title">
      <button className="app-overlay-backdrop overlay-backdrop" type="button" onClick={closeOverlay} aria-label="Wens toevoegen sluiten" />
      <div className="app-overlay-panel wishlist-overlay-panel">
        <form className="card form wishlist-smart-form" action={action}>
          <div className="section-head">
            <div>
              <h2 id="wishlist-add-title">Wens toevoegen</h2>
              <p className="muted">Plak eerst een productlink; de app vult aan wat hij kan vinden.</p>
            </div>
            <button className="icon-button" type="button" onClick={closeOverlay} title="Wens toevoegen sluiten" aria-label="Wens toevoegen sluiten">
              <X size={17} />
            </button>
          </div>
          <div className="field">
            <label htmlFor="wishlist-url">Link</label>
            <div className="input-with-icon">
              <Search size={16} />
              <input id="wishlist-url" name="url" type="url" placeholder="https://..." value={url} onChange={onUrlChange} />
            </div>
            <p className={`field-hint preview-${previewState}`}>
              {previewState === "loading" && <Loader2 size={14} className="spin" />}
              {previewMessage}
            </p>
          </div>
          {imageUrl && (
            <div className="wishlist-form-preview">
              <img src={imageUrl} alt="" />
              <div>
                <strong>{title || "Productafbeelding gevonden"}</strong>
                <span>{[category, price].filter(Boolean).join(" · ") || "Preview uit link"}</span>
              </div>
            </div>
          )}
          <div className="field">
            <label htmlFor="wishlist-title">Titel</label>
            <input id="wishlist-title" name="title" required placeholder="Bijv. LEGO set, boekenbon, koptelefoon" value={title} onChange={(event) => setTitle(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="wishlist-desired-by">Voor wie</label>
            {memberOptions.length > 0 ? (
              <select id="wishlist-desired-by" name="desired_by" defaultValue="">
                <option value="">Huishouden</option>
                {memberOptions.map((member) => (
                  <option value={member.name} key={member.id}>
                    {member.name}
                  </option>
                ))}
              </select>
            ) : (
              <input id="wishlist-desired-by" name="desired_by" placeholder="Gezinslid of huishouden" />
            )}
          </div>
          <div className="quick-field-grid">
            <div className="field">
              <label htmlFor="wishlist-category">Categorie</label>
              <input id="wishlist-category" name="category" value={category} onChange={(event) => setCategory(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="wishlist-price">Richtprijs</label>
              <input id="wishlist-price" name="price" inputMode="decimal" placeholder="Bijv. 24,95" value={price} onChange={(event) => setPrice(event.target.value)} />
            </div>
          </div>
          <div className="field">
            <label htmlFor="wishlist-image-url">Afbeelding URL</label>
            <input id="wishlist-image-url" name="image_url" type="url" placeholder="Optioneel" value={imageUrl} onChange={(event) => setImageUrl(event.target.value)} />
          </div>
          <fieldset className="quick-kind-picker wishlist-purchase-mode">
            <legend>Koopmodus</legend>
            <label className="wishlist-mode-pill">
              <input type="radio" name="purchase_mode" value="single" defaultChecked />
              <span>Eenmalig</span>
            </label>
            <label className="wishlist-mode-pill">
              <input type="radio" name="purchase_mode" value="repeatable" />
              <span>Herhaalbaar</span>
            </label>
          </fieldset>
          <div className="field">
            <label htmlFor="wishlist-description">Notitie</label>
            <textarea id="wishlist-description" name="description" rows={3} placeholder="Maat, kleur, alternatief of instructie" />
          </div>
          <label className="check-row">
            <input type="checkbox" name="is_public" defaultChecked />
            Extern zichtbaar maken op de gedeelde wishlist
          </label>
          <button className="button primary">
            <Gift size={17} /> Wens opslaan
          </button>
        </form>
      </div>
    </div>
  );
}
