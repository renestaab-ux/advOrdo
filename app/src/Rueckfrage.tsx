export function Rueckfrage({
  frage,
  erklaerung,
  ja,
  onJa,
  onNein,
}: {
  frage: string;
  erklaerung: string;
  ja: string;
  onJa: () => void;
  onNein: () => void;
}) {
  return (
    <div className="rueckfrage" role="alertdialog" aria-label={frage}>
      <strong>{frage}</strong>
      <p>{erklaerung}</p>
      <div className="aktionen">
        <button className="gefahr-voll" onClick={onJa}>
          {ja}
        </button>
        <button className="zweitrangig" onClick={onNein} autoFocus>
          Abbrechen
        </button>
      </div>
    </div>
  );
}
