import { useState } from "react";
import RoomPointsTable from "../components/RoomPointsTable";
import RoomPolygonEditor from "../components/RoomPolygonEditor";
import RoomsList from "../components/RoomsList";
import { useProjectStore } from "../store/projectStore";

export default function ProjectCreatePage() {
  const [projectName, setProjectName] = useState("");

  const activeRoomIndex = useProjectStore((state) => state.activeRoomIndex);
  const activeRoom = useProjectStore((state) => state.rooms[activeRoomIndex]);
  const rooms = useProjectStore((state) => state.rooms);
  const setHeight = useProjectStore((state) => state.setHeight);

  const handleNext = () => {
    if (!projectName) {
      alert("Пожалуйста, введите название проекта!");
      return;
    }

    const allRoomsValid = rooms.every(
      (r) => r.name.trim() !== "" && r.height !== "" && Number(r.height) > 0,
    );

    if (!allRoomsValid) {
      alert(
        "Ошибка! Убедитесь, что у всех комнат задано имя и корректная высота потолка.",
      );
      return;
    }

    alert(
      `Супер! Данные сохранены.\nПроект: ${projectName}\nВсего комнат: ${rooms.length}`,
    );
  };

  return (
    <div style={{ width: "100%", maxWidth: "560px", padding: "20px", boxSizing: "border-box" }}>
      <RoomsList />

      <div
        style={{
          fontSize: "11px",
          letterSpacing: ".16em",
          textTransform: "uppercase",
          color: "#B0B0B0",
          marginBottom: "14px",
        }}
      >
        Проект · план помещения
      </div>
      <h2 style={{ marginTop: 0, marginBottom: "20px" }}>Создание проекта</h2>

      <div style={{ marginBottom: "15px" }}>
        <label style={{ fontSize: "13px", color: "#6B6B6B" }}>Название проекта:</label>
        <input
          type="text"
          placeholder="Например: Ремонт квартиры"
          value={projectName}
          onChange={(e) => setProjectName(e.target.value)}
          style={{
            width: "100%",
            padding: "8px 10px",
            marginTop: "5px",
            background: "#fff",
            color: "var(--text-h)",
            border: "1px solid var(--border)",
            borderRadius: "4px",
            boxSizing: "border-box",
          }}
        />
      </div>

      <div style={{ marginBottom: "15px" }}>
        <label style={{ fontSize: "13px", color: "#6B6B6B" }}>Высота потолка помещения (м):</label>
        <input
          type="number"
          step="0.1"
          placeholder="2.7"
          value={activeRoom.height}
          onChange={(e) => setHeight(e.target.value)}
          style={{
            width: "100%",
            padding: "8px 10px",
            marginTop: "5px",
            background: "#fff",
            color: "var(--text-h)",
            border: "1px solid var(--border)",
            borderRadius: "4px",
            boxSizing: "border-box",
          }}
        />
      </div>

      <div style={{ marginTop: "20px" }}>
        <RoomPolygonEditor />
      </div>

      <div style={{ marginTop: "20px" }}>
        <RoomPointsTable />
      </div>

      <button
        onClick={handleNext}
        style={{
          padding: "10px 20px",
          cursor: "pointer",
          marginTop: "25px",
          background: "var(--text-h)",
          color: "#fff",
          border: "none",
          borderRadius: "3px",
          fontSize: "13px",
          letterSpacing: ".01em",
        }}
      >
        Перейти к рисованию
      </button>
    </div>
  );
}
